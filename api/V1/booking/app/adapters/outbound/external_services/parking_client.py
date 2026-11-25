"""Implémentation HTTP du port ParkingPort, alignée sur le service Parking
(voir son Swagger : /docs) :
GET /parking/availability/{catégorie}/booking -> {spot_available, ...}."""

from app.domain.enums import PlaceType
from app.ports.parking import ParkingPort

from .http_client import http_client

class HttpParkingClient(ParkingPort):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def get_booking_capacity(self, place_type: PlaceType) -> int:
        # Les codes de Booking sont ceux de Parking : pas de correspondance.
        category = place_type.value
        async with http_client(self._timeout, self._headers) as client:
            resp = await client.get(f"{self._base_url}/parking/availability/{category}/booking")
            resp.raise_for_status()
            return int(resp.json()["spot_available"])
