"""Package init for the scraper module."""
from .renfe import RenfeScraper, check_dog_availability, PLAYWRIGHT_AVAILABLE
from .models import DogAvailability, TrainResult, SearchResult, Station

__all__ = [
    "RenfeScraper",
    "check_dog_availability",
    "PLAYWRIGHT_AVAILABLE",
    "DogAvailability",
    "TrainResult",
    "SearchResult",
    "Station",
]
