"""
Renfe Dog Availability Scraper — Playwright-based automation.

Navigates the Renfe booking flow to check if the "Perros hasta 40 kg" addon
is available for each pet-friendly train on a given route and date.

Flow:
  1. Go to renfe.com
  2. Fill origin, destination, date → search
  3. Parse train list, identify pet-friendly trains (🐾 icon)
  4. For each pet-friendly train:
     a. Select "Elige Estándar" fare
     b. Advance to passenger/extras step
     c. Check if "Perros hasta 40 kg" addon is available or "Agotado"
     d. Record result
     e. Go back to results list
  5. Return all results
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Callable, Optional

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright,
        TimeoutError as PlaywrightTimeout,
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None
    Browser = Any  # type: ignore
    BrowserContext = Any  # type: ignore
    Page = Any  # type: ignore
    Playwright = Any  # type: ignore

    class PlaywrightTimeout(Exception):  # type: ignore
        pass

from .models import DogAvailability, TrainResult, SearchResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# DOM Selectors — centralised so they're easy to update when Renfe
# inevitably changes their frontend.
# ─────────────────────────────────────────────────────────────────────

class Selectors:
    """CSS / Playwright selectors for the Renfe website.

    When Renfe changes their DOM, update ONLY this class.
    Selectors use Playwright's text/role locator syntax where possible
    for resilience against class-name churn.
    """

    # ── Cookie consent ──
    COOKIE_ACCEPT = "button#onetrust-accept-btn-handler"

    # ── Search form (homepage) ──
    ORIGIN_INPUT = "#origin, input[placeholder*='origen'], input[placeholder*='departure'], input[placeholder*='salida']"
    DESTINATION_INPUT = "#destination, input[placeholder*='destino'], input[placeholder*='arrival'], input[placeholder*='llegada']"
    AUTOCOMPLETE_ITEMS = "[role='option'], .rf-input-autocomplete-alternative__options li, ul.p-autocomplete-items li"
    DATE_INPUT = "#first-input, input[formcontrolname='departureDate'], input[aria-label*='fecha']"
    SEARCH_BUTTON = "button:has-text('Buscar billete'), button[type='submit'], button:has-text('Buscar')"

    # ── Search results page (venta.renfe.com) ──
    TRAIN_ROW = "div.trayectoRow, [id^='tren_'], .item-tren, .trayecto, .travel-list__item"
    TRAIN_PET_ICON = "img[src*='huella_perro'], img[src*='perro'], .icon-pet, .icon-mascota, [class*='pet']"
    TRAIN_CODE = ".train-number, .tren-numero, .travel-list__train-code"
    TRAIN_DEPARTURE = ".departure-time, .hora-salida, .travel-list__departure"
    TRAIN_ARRIVAL = ".arrival-time, .hora-llegada, .travel-list__arrival"
    TRAIN_DURATION = ".duration, .duracion, .travel-list__duration"
    TRAIN_PRICE = ".price, .precio, .travel-list__price"
    TRAIN_PRODUCT = ".product-name, .producto, .travel-list__product"

    # ── Fare selection ──
    FARE_PRICE_CARD = "span.precio-cards"
    FARE_ELIGE = "div:has-text('Elige'):has(span.precio-cards), [class*='elige'], button:has-text('Elige')"
    FARE_BASICA = "div:has-text('Básica'):has(span.precio-cards), [class*='basica'], button:has-text('Básica')"
    CONTINUE_BUTTON = "button:has-text('Seleccionar'), button:has-text('Continuar'), button:has-text('Continue')"
    MODAL_CLOSE = "button.close, [aria-label='Cerrar'], button:has-text('×')"

    # ── Passenger / extras step ──
    DOG_ADDON_AVAILABLE = "[class*='perro'], [class*='mascota'], label:has-text('Perros hasta 40'), label:has-text('Mascota hasta 40'), [data-addon*='perro'], [data-addon*='pet']"
    DOG_ADDON_SOLD_OUT = "[class*='agotado'], [class*='sold-out'], [class*='disabled']:has-text('perro'), [class*='disabled']:has-text('mascota')"
    ADDON_SECTION = ".extras, .complementos, .ancillaries, [class*='addon'], [class*='extra']"

    # ── Navigation ──
    BACK_BUTTON = "button:has-text('Volver'), button:has-text('Back'), a:has-text('Volver'), [class*='back']"
    MODIFY_SEARCH = "button:has-text('Modificar'), a:has-text('Modificar'), button:has-text('Modify')"


class RenfeScraper:
    """Playwright-based scraper that checks large dog availability on Renfe trains."""

    def __init__(
        self,
        headless: bool = True,
        slow_mo: int = 0,
        timeout_ms: int = 60_000,
        user_agent: str | None = None,
    ):
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    async def start(self):
        """Launch the browser."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed in this environment.")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        logger.info("Browser launched (headless=%s)", self.headless)

    async def stop(self):
        """Close the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    async def _new_context(self) -> BrowserContext:
        """Create a fresh browser context with stealth settings."""
        assert self._browser, "Browser not started. Call start() first."
        context = await self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1440, "height": 900},
            locale="es-ES",
            timezone_id="Europe/Madrid",
            java_script_enabled=True,
        )
        # Stealth: remove webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // Remove Playwright-specific properties
            delete window.__playwright;
            delete window.__pw_manual;
        """)
        return context

    async def search_and_check(
        self,
        origin: str,
        destination: str,
        date: str,
        on_progress: Callable | None = None,
    ) -> SearchResult:
        """
        Full scraping flow: search trains and check dog availability.

        Args:
            origin: Origin station name (e.g. "Madrid" or "MADRID-PUERTA DE ATOCHA")
            destination: Destination station name
            date: Travel date as "DD/MM/YYYY"
            on_progress: Optional async callback for progress updates.
                         Called with (event_type: str, data: dict)

        Returns:
            SearchResult with all trains and their dog availability status.
        """
        result = SearchResult(
            origin_code=origin,
            destination_code=destination,
            date=date,
        )

        context = await self._new_context()
        page = await context.new_page()
        page.set_default_timeout(self.timeout_ms)

        try:
            # --- Step 1: Navigate to Renfe ---
            await self._emit(on_progress, "searching", {"message": "Navegando a renfe.com..."})
            await page.goto("https://www.renfe.com/es/es", wait_until="domcontentloaded")
            logger.info("Loaded renfe.com")

            # Accept cookies
            await self._accept_cookies(page)
            await page.wait_for_timeout(1000)

            # --- Step 2: Fill search form ---
            await self._emit(on_progress, "searching", {"message": "Rellenando formulario de búsqueda..."})
            await self._fill_search_form(page, origin, destination, date)

            # --- Step 3: Click search ---
            await self._click_search(page)
            await self._emit(on_progress, "searching", {"message": "Buscando trenes..."})

            # Wait for results to load
            await page.wait_for_timeout(3000)

            # --- Step 4: Parse train list ---
            trains = await self._parse_train_list(page)
            logger.info("Found %d trains", len(trains))

            if not trains:
                # Try to detect if we got redirected or there are no results
                await self._emit(on_progress, "searching", {
                    "message": "No se encontraron trenes. Capturando página para diagnóstico..."
                })
                # Save a screenshot for debugging
                await page.screenshot(path="/tmp/renfe_no_results.png")
                result.error = "No se encontraron trenes para esta ruta y fecha."
                result.checked_at = datetime.now().isoformat()
                return result

            await self._emit(on_progress, "searching", {
                "message": f"Encontrados {len(trains)} trenes",
                "total": len(trains),
            })

            pet_friendly_trains = [t for t in trains if t.pet_friendly]
            non_pet_trains = [t for t in trains if not t.pet_friendly]

            # Mark non-pet-friendly trains immediately
            for t in non_pet_trains:
                t.large_dog_available = DogAvailability.NOT_SUPPORTED
                await self._emit(on_progress, "result", t.to_dict())

            # --- Step 5: Check each pet-friendly train ---
            for i, train in enumerate(pet_friendly_trains):
                await self._emit(on_progress, "checking", {
                    "trainCode": f"{train.product_name} {train.train_code}",
                    "index": i + 1,
                    "total": len(pet_friendly_trains),
                    "message": f"Comprobando {train.product_name} {train.train_code}...",
                })

                try:
                    availability = await self._check_dog_addon(page, train, i)
                    train.large_dog_available = availability
                except Exception as e:
                    logger.error("Error checking train %s: %s", train.train_code, e)
                    train.large_dog_available = DogAvailability.ERROR
                    train.error_message = str(e)

                await self._emit(on_progress, "result", train.to_dict())

                # Small delay between checks to avoid detection
                await page.wait_for_timeout(1000)

            result.trains = non_pet_trains + pet_friendly_trains
            result.checked_at = datetime.now().isoformat()

        except PlaywrightTimeout as e:
            logger.error("Timeout during scraping: %s", e)
            result.error = f"Timeout: la página de Renfe tardó demasiado en responder."
            # Save screenshot for debugging
            try:
                await page.screenshot(path="/tmp/renfe_timeout.png")
            except Exception:
                pass
        except Exception as e:
            logger.error("Scraping error: %s", e, exc_info=True)
            result.error = f"Error durante el scraping: {str(e)}"
            try:
                await page.screenshot(path="/tmp/renfe_error.png")
            except Exception:
                pass
        finally:
            await context.close()

        return result

    # ─── Private helpers ────────────────────────────────────────────

    async def _emit(self, callback, event_type: str, data: dict):
        """Send a progress event to the callback."""
        if callback:
            await callback(event_type, data)

    async def _accept_cookies(self, page: Page):
        """Dismiss the cookie consent banner if present."""
        try:
            cookie_btn = page.locator(Selectors.COOKIE_ACCEPT)
            if await cookie_btn.is_visible(timeout=3000):
                await cookie_btn.click()
                logger.info("Cookie consent accepted")
                await page.wait_for_timeout(500)
        except (PlaywrightTimeout, Exception):
            logger.debug("No cookie banner found or already dismissed")

    async def _fill_search_form(self, page: Page, origin: str, destination: str, date: str):
        """Fill the origin, destination, and date fields in the search form."""

        # --- Origin ---
        origin_input = page.locator(Selectors.ORIGIN_INPUT).first
        await origin_input.click()
        await page.wait_for_timeout(300)
        await origin_input.fill("")
        await origin_input.type(origin, delay=80)
        await page.wait_for_timeout(800)

        # Click first autocomplete result
        autocomplete = page.locator(Selectors.AUTOCOMPLETE_ITEMS).first
        try:
            await autocomplete.wait_for(state="visible", timeout=5000)
            await autocomplete.click()
            logger.info("Selected origin: %s", origin)
        except PlaywrightTimeout:
            logger.warning("Origin autocomplete didn't appear, trying to press Enter")
            await origin_input.press("Enter")

        await page.wait_for_timeout(500)

        # --- Destination ---
        dest_input = page.locator(Selectors.DESTINATION_INPUT).first
        await dest_input.click()
        await page.wait_for_timeout(300)
        await dest_input.fill("")
        await dest_input.type(destination, delay=80)
        await page.wait_for_timeout(800)

        autocomplete = page.locator(Selectors.AUTOCOMPLETE_ITEMS).first
        try:
            await autocomplete.wait_for(state="visible", timeout=5000)
            await autocomplete.click()
            logger.info("Selected destination: %s", destination)
        except PlaywrightTimeout:
            logger.warning("Destination autocomplete didn't appear, trying Enter")
            await dest_input.press("Enter")

        await page.wait_for_timeout(500)

        # --- Date ---
        # Renfe date picker is tricky — it might be a calendar widget
        try:
            # Set the date directly by removing readonly attribute and dispatching events
            await page.evaluate(
                """
                ([val]) => {
                    const selectors = ['#first-input', "input[formcontrolname='departureDate']", "input[placeholder*='Fecha ida']"];
                    for (const s of selectors) {
                        const el = document.querySelector(s);
                        if (el) {
                            el.removeAttribute('readonly');
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            break;
                        }
                    }
                }
                """,
                [date],
            )
            logger.info("Set date on Renfe: %s", date)
            await page.wait_for_timeout(300)
        except Exception as e:
            logger.warning("Could not set date on Renfe form: %s", e)

    async def _click_search(self, page: Page):
        """Click the search button and wait for results."""
        search_btn = page.locator(Selectors.SEARCH_BUTTON).first
        await search_btn.click()
        logger.info("Search button clicked")

        # Wait for navigation or results loading
        # Renfe may redirect to a results page or load results dynamically
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            logger.debug("Network didn't go idle, proceeding anyway")

        await page.wait_for_timeout(2000)

    async def _parse_train_list(self, page: Page) -> list[TrainResult]:
        """Parse the search results page to extract train information."""
        trains = []

        # Save page content for debugging
        content = await page.content()
        logger.debug("Page content length: %d chars", len(content))

        # Try to find train rows using various selectors
        rows = page.locator(Selectors.TRAIN_ROW)
        count = await rows.count()

        if count == 0:
            logger.warning("No train rows found with primary selectors. Trying alternative discovery...")
            # Try a broader approach — look for any element with schedule data
            # This is where we'd need DOM exploration to find the right selectors
            await page.screenshot(path="/tmp/renfe_results_page.png")

            # Save HTML for offline analysis
            with open("/tmp/renfe_results_page.html", "w") as f:
                f.write(content)
            logger.info("Saved results page HTML to /tmp/renfe_results_page.html for analysis")
            return trains

        logger.info("Found %d train rows", count)

        for i in range(count):
            row = rows.nth(i)

            try:
                # Check for pet icon
                pet_icon = row.locator(Selectors.TRAIN_PET_ICON)
                has_pet = await pet_icon.count() > 0

                # Extract train info
                train_code = await self._safe_text(row.locator(Selectors.TRAIN_CODE))
                departure = await self._safe_text(row.locator(Selectors.TRAIN_DEPARTURE))
                arrival = await self._safe_text(row.locator(Selectors.TRAIN_ARRIVAL))
                duration = await self._safe_text(row.locator(Selectors.TRAIN_DURATION))
                price_text = await self._safe_text(row.locator(Selectors.TRAIN_PRICE))
                product = await self._safe_text(row.locator(Selectors.TRAIN_PRODUCT))

                # Parse price
                price = None
                if price_text:
                    price_match = re.search(r"(\d+[.,]\d{2})", price_text)
                    if price_match:
                        price = float(price_match.group(1).replace(",", "."))

                train = TrainResult(
                    train_code=train_code or f"train-{i}",
                    product_name=product or "Unknown",
                    departure=departure or "??:??",
                    arrival=arrival or "??:??",
                    duration=duration or "",
                    origin_name="",  # Filled from station data
                    destination_name="",
                    pet_friendly=has_pet,
                    price=price,
                )
                trains.append(train)

            except Exception as e:
                logger.error("Error parsing train row %d: %s", i, e)

        return trains

    async def _check_dog_addon(self, page: Page, train: TrainResult, index: int) -> DogAvailability:
        """
        Navigate into a train's booking flow to check dog addon availability.

        This is the critical function — it must:
        1. Click on the train in the results list
        2. Select the "Elige Estándar" fare
        3. Reach the addons/extras step
        4. Check if "Perros hasta 40 kg" is available or sold out
        5. Go back to the results list for the next train
        """
        logger.info("Checking dog addon for train %s (index %d)", train.train_code, index)

        try:
            # Step 1: Click on this train row
            rows = page.locator(Selectors.TRAIN_ROW)
            row = rows.nth(index)
            await row.click()
            await page.wait_for_timeout(1500)

            # Step 2: Select "Elige Estándar" fare
            elige_btn = page.locator(Selectors.FARE_ELIGE).first
            try:
                await elige_btn.wait_for(state="visible", timeout=5000)
                await elige_btn.click()
                logger.info("Selected 'Elige Estándar' fare")
                await page.wait_for_timeout(1000)
            except PlaywrightTimeout:
                logger.warning("Elige fare not found, trying Básica (for AVLO)")
                basica_btn = page.locator(Selectors.FARE_BASICA).first
                try:
                    await basica_btn.click()
                    logger.info("Selected 'Básica' fare (AVLO)")
                    await page.wait_for_timeout(1000)
                except Exception:
                    logger.error("Could not select any fare")
                    return DogAvailability.ERROR

            # Step 3: Click continue to advance to passenger/extras
            continue_btn = page.locator(Selectors.CONTINUE_BUTTON).first
            try:
                await continue_btn.wait_for(state="visible", timeout=5000)
                await continue_btn.click()
                await page.wait_for_timeout(2000)
            except PlaywrightTimeout:
                logger.warning("Continue button not found, page may have auto-advanced")

            # Step 4: Check for dog addon availability
            # Look for the dog addon in the extras/ancillaries section
            addon_section = page.locator(Selectors.ADDON_SECTION)
            try:
                await addon_section.first.wait_for(state="visible", timeout=8000)
            except PlaywrightTimeout:
                # Maybe we need to click "Continuar" again to reach extras
                try:
                    continue_btn2 = page.locator(Selectors.CONTINUE_BUTTON).first
                    await continue_btn2.click()
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

            # Check for available dog addon
            dog_available = page.locator(Selectors.DOG_ADDON_AVAILABLE)
            dog_sold_out = page.locator(Selectors.DOG_ADDON_SOLD_OUT)

            available_count = await dog_available.count()
            sold_out_count = await dog_sold_out.count()

            # Also check by text content on the page
            page_text = await page.inner_text("body")

            availability = DogAvailability.ERROR

            if "Perros hasta 40" in page_text or "perro" in page_text.lower():
                if "agotado" in page_text.lower() or "no disponible" in page_text.lower():
                    availability = DogAvailability.SOLD_OUT
                    train.dog_addon_price = 40.0
                elif available_count > 0:
                    availability = DogAvailability.AVAILABLE
                    train.dog_addon_price = 40.0
                else:
                    # Dog addon section exists but unclear status
                    availability = DogAvailability.AVAILABLE
                    train.dog_addon_price = 40.0
            elif sold_out_count > 0:
                availability = DogAvailability.SOLD_OUT
            elif available_count > 0:
                availability = DogAvailability.AVAILABLE
                train.dog_addon_price = 40.0
            else:
                # Could not find dog addon at all — might mean not supported or page structure changed
                logger.warning("Could not find dog addon section for train %s", train.train_code)
                await page.screenshot(path=f"/tmp/renfe_addon_check_{train.train_code}.png")
                availability = DogAvailability.ERROR
                train.error_message = "No se pudo determinar la disponibilidad"

            logger.info("Train %s dog availability: %s", train.train_code, availability.value)

        except Exception as e:
            logger.error("Error during addon check for %s: %s", train.train_code, e)
            availability = DogAvailability.ERROR
            train.error_message = str(e)

        # Step 5: Go back to results list
        try:
            await self._go_back_to_results(page)
        except Exception as e:
            logger.error("Error going back to results: %s", e)
            # If we can't go back, subsequent trains will fail
            # Try a full page reload to the search results
            await page.go_back()
            await page.wait_for_timeout(2000)

        return availability

    async def _go_back_to_results(self, page: Page):
        """Navigate back to the train results list."""
        # Try clicking back button
        back_btn = page.locator(Selectors.BACK_BUTTON).first
        try:
            if await back_btn.is_visible(timeout=2000):
                await back_btn.click()
                await page.wait_for_timeout(1500)
                return
        except (PlaywrightTimeout, Exception):
            pass

        # Try modify search
        modify_btn = page.locator(Selectors.MODIFY_SEARCH).first
        try:
            if await modify_btn.is_visible(timeout=2000):
                await modify_btn.click()
                await page.wait_for_timeout(1500)
                return
        except (PlaywrightTimeout, Exception):
            pass

        # Fall back to browser back
        await page.go_back()
        await page.wait_for_timeout(2000)

        # May need multiple backs depending on how deep we went
        rows = page.locator(Selectors.TRAIN_ROW)
        if await rows.count() == 0:
            await page.go_back()
            await page.wait_for_timeout(2000)

    async def _safe_text(self, locator, timeout: int = 1000) -> str | None:
        """Safely extract text content from a locator."""
        try:
            if await locator.count() > 0:
                return (await locator.first.inner_text(timeout=timeout)).strip()
        except Exception:
            pass
        return None


# ─────────────────────────────────────────────────────────────────────
# Convenience function for standalone usage
# ─────────────────────────────────────────────────────────────────────

async def check_dog_availability(
    origin: str,
    destination: str,
    date: str,
    headless: bool = True,
    on_progress: Callable | None = None,
) -> SearchResult:
    """
    One-shot convenience: launch browser, check availability, close.

    Args:
        origin: Origin station name (e.g. "Madrid")
        destination: Destination station name (e.g. "Barcelona")
        date: Travel date as "DD/MM/YYYY"
        headless: Run browser headlessly
        on_progress: Async callback for progress events

    Returns:
        SearchResult with all trains and availability.
    """
    async with RenfeScraper(headless=headless, slow_mo=100 if not headless else 0) as scraper:
        return await scraper.search_and_check(origin, destination, date, on_progress)
