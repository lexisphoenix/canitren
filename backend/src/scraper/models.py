"""Data models for train search results and dog availability."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional
import json


class DogAvailability(str, Enum):
    """Status of large dog (10-40kg) addon availability on a train."""

    AVAILABLE = "available"          # ✅ Addon is bookable
    SOLD_OUT = "sold_out"            # ❌ Addon exists but 0 slots left
    NOT_SUPPORTED = "not_supported"  # 🚫 Train type doesn't allow large dogs
    CHECKING = "checking"            # ⏳ Currently being checked
    ERROR = "error"                  # ⚠️ Could not determine
    UNKNOWN = "unknown"              # ❓ Not yet checked


@dataclass
class TrainResult:
    """A single train with its dog availability status."""

    train_code: str                          # e.g. "03201"
    product_name: str                        # e.g. "AVE", "AVLO", "Alvia"
    departure: str                           # e.g. "06:30"
    arrival: str                             # e.g. "09:10"
    duration: str                            # e.g. "2h 40m"
    origin_name: str                         # e.g. "MADRID-PUERTA DE ATOCHA"
    destination_name: str                    # e.g. "BARCELONA-SANTS"
    pet_friendly: bool                       # Does this train type support any pets?
    large_dog_available: DogAvailability = DogAvailability.UNKNOWN
    price: Optional[float] = None            # Ticket price in EUR
    dog_addon_price: Optional[float] = None  # Dog addon price (usually €40)
    fare_name: Optional[str] = None          # e.g. "Elige Estándar"
    booking_url: Optional[str] = None        # Deep link to Renfe booking
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["large_dog_available"] = self.large_dog_available.value
        # Convert to camelCase for the frontend
        return {
            "trainCode": self.train_code,
            "productName": self.product_name,
            "departure": self.departure,
            "arrival": self.arrival,
            "duration": self.duration,
            "originName": self.origin_name,
            "destinationName": self.destination_name,
            "petFriendly": self.pet_friendly,
            "largeDogAvailable": self.large_dog_available.value,
            "price": self.price,
            "dogAddonPrice": self.dog_addon_price,
            "fareName": self.fare_name,
            "bookingUrl": self.booking_url,
            "errorMessage": self.error_message,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class SearchResult:
    """Complete result of a route search."""

    origin_code: str
    destination_code: str
    date: str
    trains: list[TrainResult] = field(default_factory=list)
    checked_at: Optional[str] = None
    cached: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "originCode": self.origin_code,
            "destinationCode": self.destination_code,
            "date": self.date,
            "trains": [t.to_dict() for t in self.trains],
            "checkedAt": self.checked_at,
            "cached": self.cached,
            "error": self.error,
        }


@dataclass
class Station:
    """A Renfe station."""

    code: str     # Renfe numeric code, e.g. "60000"
    name: str     # Station name, e.g. "MADRID-PUERTA DE ATOCHA"

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name}


# Product codes from the Renfe real-time fleet JSON
# These codes map to commercial product types
PRODUCT_CODES = {
    2: "AVE",
    3: "Alvia",
    4: "Euromed",
    5: "Intercity",
    6: "AVLO",
    11: "Talgo",
    16: "Media Distancia",
    18: "Regional",
    19: "Regional Exprés",
    28: "Avant",
}

# Train types that support large dogs (10-40kg)
LARGE_DOG_COMPATIBLE_PRODUCTS = {"AVE", "AVLO", "Alvia", "Euromed", "Intercity", "Avant", "Media Distancia"}
