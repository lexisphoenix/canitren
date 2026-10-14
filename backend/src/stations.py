"""
Station data service — fetches and caches station names/codes.

Uses the RadarDeTrenes API as primary source (free, public, no auth).
Falls back to a hardcoded list of major stations.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .scraper.models import Station
from .config import config

logger = logging.getLogger(__name__)

# Hardcoded major stations as fallback (code → name)
MAJOR_STATIONS = {
    "60000": "MADRID-PUERTA DE ATOCHA",
    "17000": "MADRID-CHAMARTÍN-CLARA CAMPOAMOR",
    "71801": "BARCELONA-SANTS",
    "79300": "BARCELONA-PASSEIG DE GRÀCIA",
    "51003": "SEVILLA-SANTA JUSTA",
    "65400": "VALENCIA-JOAQUÍN SOROLLA",
    "54413": "MÁLAGA-MARÍA ZAMBRANO",
    "05000": "ZARAGOZA-DELICIAS",
    "20201": "BILBAO-ABANDO INDALECIO PRIETO",
    "31400": "A CORUÑA-SAN CRISTÓBAL",
    "10600": "VALLADOLID-CAMPO GRANDE",
    "08223": "VIGO-GUIXAR",
    "81002": "ALICANTE/ALACANT TERMINAL",
    "50600": "CÓRDOBA",
    "94400": "SAN SEBASTIÁN/DONOSTIA",
    "37600": "TOLEDO",
    "15400": "LEÓN",
    "40700": "MURCIA DEL CARMEN",
    "35400": "CÁCERES",
    "30110": "SALAMANCA",
    "18000": "CIUDAD REAL",
    "04600": "TARRAGONA",
    "04307": "CAMP DE TARRAGONA",
    "71500": "GIRONA",
    "04101": "LLEIDA-PIRINEUS",
    "14200": "HUESCA",
    "21010": "FERROL",
    "55200": "ALGECIRAS",
    "43100": "CARTAGENA",
    "79400": "FIGUERES-VILAFANT",
    "56310": "ALMERÍA",
    "70600": "GUADALAJARA-YEBES",
    "37200": "PUERTOLLANO",
}

# In-memory station cache
_stations_cache: list[Station] | None = None


async def get_all_stations() -> list[Station]:
    """Fetch the full station catalogue, cached in memory."""
    global _stations_cache

    if _stations_cache is not None:
        return _stations_cache

    # Try RadarDeTrenes API first
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{config.radar_api_base}/stations?type=ld")
            resp.raise_for_status()
            data = resp.json()

            stations = []
            for s in data.get("stations", []):
                code = s.get("code", "")
                name = s.get("name", s.get("longName", ""))
                if code and name:
                    stations.append(Station(code=str(code), name=name.upper()))

            if stations:
                _stations_cache = stations
                logger.info("Loaded %d stations from RadarDeTrenes API", len(stations))
                return _stations_cache

    except Exception as e:
        logger.warning("Failed to fetch stations from RadarDeTrenes: %s", e)

    # Fallback to hardcoded list
    _stations_cache = [Station(code=c, name=n) for c, n in MAJOR_STATIONS.items()]
    logger.info("Using %d hardcoded major stations", len(_stations_cache))
    return _stations_cache


async def search_stations(query: str) -> list[Station]:
    """Search stations by name (case-insensitive substring match)."""
    all_stations = await get_all_stations()
    q = query.upper().strip()

    if not q:
        # Return popular stations
        popular_codes = ["60000", "71801", "51003", "65400", "54413", "05000", "17000", "20201"]
        return [s for s in all_stations if s.code in popular_codes]

    # Score-based matching: exact prefix > word start > substring
    scored = []
    for s in all_stations:
        name = s.name.upper()
        if name.startswith(q):
            scored.append((0, s))  # Best: starts with query
        elif any(word.startswith(q) for word in name.split()):
            scored.append((1, s))  # Good: word starts with query
        elif q in name:
            scored.append((2, s))  # OK: substring match
        elif q in s.code:
            scored.append((3, s))  # Also: code match

    scored.sort(key=lambda x: x[0])
    return [s for _, s in scored[:15]]


def get_station_name(code: str) -> str:
    """Get station name by code (checks hardcoded list and dynamic cache)."""
    if code in MAJOR_STATIONS:
        return MAJOR_STATIONS[code]

    if _stations_cache:
        for s in _stations_cache:
            if s.code == code:
                return s.name

    # If code is already a descriptive name or string with letters
    if any(c.isalpha() for c in code):
        return code.strip()

    return f"Estación {code}"


def get_search_term(code_or_name: str) -> str:
    """
    Get the most effective search term to type into Renfe's autocomplete input.
    E.g., "MADRID-PUERTA DE ATOCHA" -> "MADRID"
          "BARCELONA-SANTS" -> "BARCELONA"
    """
    name = get_station_name(code_or_name)
    # Split on hyphen, slash, or space to get the primary city name
    cleaned = name.split("-")[0].split("/")[0].strip()
    return cleaned if len(cleaned) >= 3 else name

