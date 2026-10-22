"""Implémentation HTTP du port VehiclesPort. Résout une plaque en
identifiant pseudonymisé ; Booking ne conserve jamais la plaque elle-même,
uniquement ce que Vehicles lui renvoie."""

import httpx

from app.ports.external_services import VehiclesPort


class HttpVehiclesClient(VehiclesPort):
    def __init__(self, base_url: str):
        self._base_url = base_url

    async def resolve_vehicle_id(self, plate: str) -> str:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{self._base_url}/resolve", json={"plate": plate})
            resp.raise_for_status()
            return resp.json()["vehicle_id"]
