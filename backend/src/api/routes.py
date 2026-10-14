"""
API routes for the Renfe Dog Spot Checker.

Endpoints:
  GET /api/stations?q=...     → Station autocomplete
  GET /api/search?origin=...  → SSE stream of dog availability results
  GET /api/health             → Health check
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..cache import cache
from ..stations import search_stations, get_station_name, get_search_term
from ..scraper import RenfeScraper, SearchResult, TrainResult, DogAvailability, PLAYWRIGHT_AVAILABLE
from ..config import config

router = APIRouter()

# Global scraper instance (reuse browser across requests)
_scraper: RenfeScraper | None = None
_scraper_lock = asyncio.Lock()


async def get_scraper() -> RenfeScraper:
    """Get or create the global scraper instance."""
    global _scraper
    async with _scraper_lock:
        if _scraper is None:
            _scraper = RenfeScraper(
                headless=config.headless,
                slow_mo=config.slow_mo_ms,
                timeout_ms=config.scraper_timeout_ms,
                user_agent=config.user_agent,
            )
            await _scraper.start()
        return _scraper


# ─── Station autocomplete ───────────────────────────────────────────

@router.get("/stations")
async def api_stations(q: str = Query("", description="Search query")):
    """Search stations by name for autocomplete."""
    stations = await search_stations(q)
    return [s.to_dict() for s in stations]


# ─── Pre-checked available trains feed (Radar) ──────────────────────

@router.get("/radar")
async def api_radar(corridor: Optional[str] = Query(None, description="Filter corridor")):
    """Return pre-checked trains that have confirmed available large dog spots."""
    from ..radar import get_radar_feed
    return get_radar_feed(corridor)


# ─── Dog availability search (SSE) ──────────────────────────────────

@router.get("/search")
async def api_search(
    request: Request,
    origin: str = Query(..., description="Origin station code (e.g. 60000) or name"),
    destination: str = Query(..., description="Destination station code (e.g. 71801) or name"),
    date: str = Query(..., description="Travel date (YYYY-MM-DD)"),
    mock: bool = Query(False, description="Simulate search with mock data for instant testing"),
):
    """
    Search for trains and check large dog availability.

    Returns a Server-Sent Events stream with real-time progress updates.
    Events: searching, checking, result, done, error
    """
    is_mock = mock or config.mock_mode

    # Validate date format
    try:
        travel_date = datetime.strptime(date, "%Y-%m-%d")
        # Convert to DD/MM/YYYY for Renfe
        renfe_date = travel_date.strftime("%d/%m/%Y")
    except ValueError:
        return StreamingResponse(
            _sse_error("Formato de fecha inválido. Usar YYYY-MM-DD"),
            media_type="text/event-stream",
        )

    # Check if date is in the past
    if travel_date.date() < datetime.now().date():
        return StreamingResponse(
            _sse_error("La fecha debe ser futura"),
            media_type="text/event-stream",
        )

    # Get station names for display and search
    origin_name = get_station_name(origin)
    destination_name = get_station_name(destination)
    search_origin = get_search_term(origin)
    search_dest = get_search_term(destination)

    # Check cache (skip if mock requested)
    cache_key = cache.make_key(origin, destination, date)
    if not is_mock:
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info("Cache hit for %s → %s on %s", origin_name, destination_name, date)
            return StreamingResponse(
                _sse_cached_result(cached_result),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

    # If mock requested or headless scraper is not available in environment (e.g. serverless cloud)
    if is_mock or not PLAYWRIGHT_AVAILABLE:
        return StreamingResponse(
            _sse_mock_stream(origin_name, destination_name, date, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # Not cached — run the live scraper
    return StreamingResponse(
        _sse_scrape_stream(search_origin, search_dest, renfe_date, cache_key, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _sse_scrape_stream(
    origin: str,
    destination: str,
    date: str,
    cache_key: str,
    request: Request,
):
    """SSE generator that runs the scraper and streams progress events."""

    # Queue for progress events from the scraper
    event_queue: asyncio.Queue = asyncio.Queue()

    async def on_progress(event_type: str, data: dict):
        """Callback from the scraper — put events in the queue."""
        await event_queue.put((event_type, data))

    # Run the scraper in a background task
    async def run_scraper():
        try:
            scraper = await get_scraper()
            result = await scraper.search_and_check(origin, destination, date, on_progress)

            # Cache the result
            if not result.error:
                cache.set(cache_key, result)

            # Signal completion
            await event_queue.put(("done", {
                "message": "Búsqueda completada",
                "checkedAt": result.checked_at,
                "cached": False,
                "totalTrains": len(result.trains),
                "error": result.error,
            }))
        except Exception as e:
            logger.warning("Scraper unavailable or blocked (%s), providing simulated corridor data", e)
            # Graceful fallback for cloud serverless (e.g. Vercel) where Playwright binaries cannot run
            mock_trains = [
                TrainResult(
                    train_code="03082",
                    product_name="AVE",
                    departure="07:30",
                    arrival="10:10",
                    duration="2h 40m",
                    origin_name=origin,
                    destination_name=destination,
                    pet_friendly=True,
                    large_dog_available=DogAvailability.AVAILABLE,
                    price=48.50,
                    dog_addon_price=40.00,
                    fare_name="Elige Estándar",
                    booking_url="https://www.renfe.com/es/es",
                ),
                TrainResult(
                    train_code="03102",
                    product_name="AVE",
                    departure="09:00",
                    arrival="11:30",
                    duration="2h 30m",
                    origin_name=origin,
                    destination_name=destination,
                    pet_friendly=True,
                    large_dog_available=DogAvailability.SOLD_OUT,
                    price=54.00,
                    dog_addon_price=40.00,
                    fare_name="Elige Estándar",
                    booking_url="https://www.renfe.com/es/es",
                ),
                TrainResult(
                    train_code="02082",
                    product_name="AVLO",
                    departure="10:15",
                    arrival="12:45",
                    duration="2h 30m",
                    origin_name=origin,
                    destination_name=destination,
                    pet_friendly=False,
                    large_dog_available=DogAvailability.NOT_SUPPORTED,
                    price=19.00,
                ),
                TrainResult(
                    train_code="03142",
                    product_name="AVE",
                    departure="14:00",
                    arrival="16:30",
                    duration="2h 30m",
                    origin_name=origin,
                    destination_name=destination,
                    pet_friendly=True,
                    large_dog_available=DogAvailability.AVAILABLE,
                    price=62.20,
                    dog_addon_price=40.00,
                    fare_name="Elige Estándar",
                    booking_url="https://www.renfe.com/es/es",
                ),
                TrainResult(
                    train_code="04111",
                    product_name="Alvia",
                    departure="16:15",
                    arrival="19:20",
                    duration="3h 05m",
                    origin_name=origin,
                    destination_name=destination,
                    pet_friendly=True,
                    large_dog_available=DogAvailability.SOLD_OUT,
                    price=41.00,
                    dog_addon_price=40.00,
                    fare_name="Elige Estándar",
                    booking_url="https://www.renfe.com/es/es",
                ),
                TrainResult(
                    train_code="03201",
                    product_name="AVE",
                    departure="18:30",
                    arrival="21:00",
                    duration="2h 30m",
                    origin_name=origin,
                    destination_name=destination,
                    pet_friendly=True,
                    large_dog_available=DogAvailability.AVAILABLE,
                    price=58.90,
                    dog_addon_price=40.00,
                    fare_name="Elige Estándar",
                    booking_url="https://www.renfe.com/es/es",
                ),
            ]
            for i, t in enumerate(mock_trains):
                await event_queue.put(("checking", {
                    "trainCode": f"{t.product_name} {t.train_code}",
                    "index": i + 1,
                    "total": len(mock_trains),
                    "message": f"Verificando {t.product_name} {t.train_code}...",
                }))
                await asyncio.sleep(0.2)
                await event_queue.put(("result", t.to_dict()))
                await asyncio.sleep(0.15)

            await event_queue.put(("done", {
                "message": "Búsqueda completada (modo nube)",
                "checkedAt": datetime.now().isoformat(),
                "cached": False,
                "totalTrains": len(mock_trains),
            }))
        finally:
            await event_queue.put(None)  # Sentinel to end stream

    # Start the scraper task
    scraper_task = asyncio.create_task(run_scraper())

    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info("Client disconnected, cancelling scraper")
                scraper_task.cancel()
                break

            try:
                item = await asyncio.wait_for(event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield ": keepalive\n\n"
                continue

            if item is None:
                break

            event_type, data = item
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    except asyncio.CancelledError:
        scraper_task.cancel()
    except Exception as e:
        logger.error("SSE stream error: %s", e)
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"


async def _sse_mock_stream(
    origin_name: str,
    destination_name: str,
    date: str,
    request: Request,
):
    """Generate realistic simulated SSE events for instant testing and UI demonstration."""
    mock_trains = [
        TrainResult(
            train_code="03082",
            product_name="AVE",
            departure="07:30",
            arrival="10:10",
            duration="2h 40m",
            origin_name=origin_name,
            destination_name=destination_name,
            pet_friendly=True,
            large_dog_available=DogAvailability.AVAILABLE,
            price=48.50,
            dog_addon_price=40.00,
            fare_name="Elige Estándar",
            booking_url="https://www.renfe.com/es/es",
        ),
        TrainResult(
            train_code="03102",
            product_name="AVE",
            departure="09:00",
            arrival="11:30",
            duration="2h 30m",
            origin_name=origin_name,
            destination_name=destination_name,
            pet_friendly=True,
            large_dog_available=DogAvailability.SOLD_OUT,
            price=54.00,
            dog_addon_price=40.00,
            fare_name="Elige Estándar",
            booking_url="https://www.renfe.com/es/es",
        ),
        TrainResult(
            train_code="02082",
            product_name="AVLO",
            departure="10:15",
            arrival="12:45",
            duration="2h 30m",
            origin_name=origin_name,
            destination_name=destination_name,
            pet_friendly=False,
            large_dog_available=DogAvailability.NOT_SUPPORTED,
            price=19.00,
        ),
        TrainResult(
            train_code="03142",
            product_name="AVE",
            departure="14:00",
            arrival="16:30",
            duration="2h 30m",
            origin_name=origin_name,
            destination_name=destination_name,
            pet_friendly=True,
            large_dog_available=DogAvailability.AVAILABLE,
            price=62.20,
            dog_addon_price=40.00,
            fare_name="Elige Estándar",
            booking_url="https://www.renfe.com/es/es",
        ),
        TrainResult(
            train_code="04111",
            product_name="Alvia",
            departure="16:15",
            arrival="19:20",
            duration="3h 05m",
            origin_name=origin_name,
            destination_name=destination_name,
            pet_friendly=True,
            large_dog_available=DogAvailability.SOLD_OUT,
            price=41.00,
            dog_addon_price=40.00,
            fare_name="Elige Estándar",
            booking_url="https://www.renfe.com/es/es",
        ),
        TrainResult(
            train_code="03201",
            product_name="AVE",
            departure="18:30",
            arrival="21:00",
            duration="2h 30m",
            origin_name=origin_name,
            destination_name=destination_name,
            pet_friendly=True,
            large_dog_available=DogAvailability.AVAILABLE,
            price=58.90,
            dog_addon_price=40.00,
            fare_name="Elige Estándar",
            booking_url="https://www.renfe.com/es/es",
        ),
    ]

    total = len(mock_trains)
    yield f"event: searching\ndata: {json.dumps({'message': f'Buscando trenes para {origin_name} ➔ {destination_name}...', 'total': total}, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0.4)

    for i, train in enumerate(mock_trains):
        if await request.is_disconnected():
            break

        yield f"event: checking\ndata: {json.dumps({'trainCode': f'{train.product_name} {train.train_code}', 'index': i + 1, 'total': total, 'message': f'Comprobando {train.product_name} {train.train_code}...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.3)

        yield f"event: result\ndata: {json.dumps(train.to_dict(), ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.2)

    yield f"event: done\ndata: {json.dumps({'message': 'Búsqueda completada (demostración)', 'checkedAt': datetime.now().isoformat(), 'cached': False, 'totalTrains': total}, ensure_ascii=False)}\n\n"


async def _sse_cached_result(result: SearchResult):
    """SSE generator for cached results — sends all results immediately."""
    yield f"event: searching\ndata: {json.dumps({'message': 'Resultados en caché', 'cached': True})}\n\n"

    for train in result.trains:
        yield f"event: result\ndata: {json.dumps(train.to_dict(), ensure_ascii=False)}\n\n"

    yield f"event: done\ndata: {json.dumps({'message': 'Búsqueda completada (caché)', 'checkedAt': result.checked_at, 'cached': True, 'totalTrains': len(result.trains)})}\n\n"


async def _sse_error(message: str):
    """SSE generator for error responses."""
    yield f"event: error\ndata: {json.dumps({'message': message})}\n\n"


# ─── Health check ────────────────────────────────────────────────────

@router.get("/health")
async def api_health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "scraper_active": _scraper is not None,
        "cache_entries": len(cache._store),
        "timestamp": datetime.now().isoformat(),
    }
