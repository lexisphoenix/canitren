"""
Renfe Dog Spot Checker — FastAPI Application

Serves both the API and the frontend static files.
Run with: uvicorn src.main:app --reload
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api.routes import router as api_router
from .config import config

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("renfe-dog-checker")

# ── App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="🐕 Renfe Dog Spot Checker",
    description="Find Renfe trains with available spots for large dogs (10-40kg)",
    version="0.1.0",
)

# API routes
app.include_router(api_router)

# Frontend — serve the single HTML file
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    """Serve the frontend index.html."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return {"error": "Frontend not found. Place index.html in the frontend/ directory."}


# Serve any other static files from frontend/
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Lifecycle ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("🐕 Renfe Dog Spot Checker starting up...")
    logger.info("  Frontend dir: %s (exists: %s)", FRONTEND_DIR, FRONTEND_DIR.exists())
    logger.info("  Headless: %s", config.headless)
    logger.info("  Cache TTL: %ds", config.cache_ttl_seconds)
    logger.info("  Debug: %s", config.debug)

    # Pre-fetch station data
    from .stations import get_all_stations
    stations = await get_all_stations()
    logger.info("  Loaded %d stations", len(stations))


@app.on_event("shutdown")
async def shutdown():
    logger.info("🐕 Shutting down...")
    # Clean up the global scraper instance
    from .api.routes import _scraper
    if _scraper:
        await _scraper.stop()
