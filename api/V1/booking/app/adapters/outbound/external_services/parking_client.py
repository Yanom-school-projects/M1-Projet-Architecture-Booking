"""Implémentation HTTP du port ParkingPort, alignée sur le service Parking
(voir son Swagger : /docs) :
GET /parking/availability/{catégorie}/booking -> {spot_available, ...}."""

import httpx

from app.domain.enums import PlaceType
from app.ports.parking import ParkingPort

# Types de place de Booking -> catégories de Parking.
PARKING_CATEGORIES = {
    PlaceType.STANDARD: "STANDARD",
    PlaceType.XL: "XL",
    PlaceType.HANDICAP: "HANDICAPPED",
    PlaceType.ELECTRIQUE: "ELECTRIC",
    PlaceType.DEUX_ROUES: "TWO_WHEELS",
}


class HttpParkingClient(ParkingPort):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def get_booking_capacity(self, place_type: PlaceType) -> int:
        category = PARKING_CATEGORIES[place_type]
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            resp = await client.get(f"{self._base_url}/parking/availability/{category}/booking")
            resp.raise_for_status()
            return int(resp.json()["spot_available"])
