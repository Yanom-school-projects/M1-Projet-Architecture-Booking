"""Implémentation HTTP du port VehiclesPort. Résout une plaque en
identifiant pseudonymisé ; Booking ne conserve jamais la plaque elle-même,
uniquement ce que Vehicles lui renvoie."""

import logging

import httpx

from app.domain.exceptions import ExternalServiceError
from app.ports.external_services import VehiclesPort

logger = logging.getLogger("booking.vehicles")


class HttpVehiclesClient(VehiclesPort):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def resolve_vehicle_id(self, plate: str) -> str:
        if not self._base_url:
            raise ExternalServiceError("Service Vehicles non configuré (VEHICLES_SERVICE_URL vide)")
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
                resp = await client.post(f"{self._base_url}/resolve", json={"plate": plate})
                resp.raise_for_status()
                return resp.json()["vehicle_id"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            # Pas de plaque dans le log : donnée personnelle.
            logger.warning("Échec de l'appel à Vehicles : %s", exc)
            raise ExternalServiceError("Service Vehicles indisponible, réservation impossible") from exc
