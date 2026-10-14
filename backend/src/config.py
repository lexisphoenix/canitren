"""Configuration for the Renfe Dog Spot Checker."""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration — override with environment variables."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8050
    debug: bool = True
    mock_mode: bool = False  # Set True or pass ?mock=true to simulate responses

    # Scraper
    headless: bool = True  # Set False to see the browser (debugging)
    scraper_timeout_ms: int = 60_000  # Max time per page navigation
    check_timeout_ms: int = 120_000  # Max time for full availability check
    slow_mo_ms: int = 0  # Slow down Playwright actions (debugging)
    max_concurrent_checks: int = 2  # Parallel browser sessions
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # Cache (in-memory for MVP, swap for Redis later)
    cache_ttl_seconds: int = 900  # 15 minutes

    # Renfe URLs
    renfe_base_url: str = "https://www.renfe.com/es/es"
    renfe_search_url: str = "https://www.renfe.com/es/es"

    # RadarDeTrenes API (for station data enrichment)
    radar_api_base: str = "https://radardetrenes.com/api/v1"

    @classmethod
    def from_env(cls) -> "Config":
        """Load config, overriding defaults from environment variables."""
        return cls(
            host=os.getenv("HOST", cls.host),
            port=int(os.getenv("PORT", cls.port)),
            debug=os.getenv("DEBUG", "true").lower() == "true",
            mock_mode=os.getenv("MOCK_MODE", "false").lower() == "true",
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            scraper_timeout_ms=int(os.getenv("SCRAPER_TIMEOUT_MS", cls.scraper_timeout_ms)),
            slow_mo_ms=int(os.getenv("SLOW_MO_MS", cls.slow_mo_ms)),
            max_concurrent_checks=int(os.getenv("MAX_CONCURRENT_CHECKS", cls.max_concurrent_checks)),
            cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", cls.cache_ttl_seconds)),
        )


config = Config.from_env()
