"""Implémentation HTTP du port VehiclesPort. Résout une plaque en
identifiant pseudonymisé ; Booking ne conserve jamais la plaque elle-même,
uniquement ce que Vehicles lui renvoie.

Contrat convenu avec l'équipe Vehicles (28 octobre) :
POST /api/vehicles/identify, corps `{licensePlate, isElectric, isDisabled,
isXl, isTwoWheels}` → `{code, pseudoId, ...}`. Le `code` est généré par
Vehicles et sert de plaque pseudonymisée : c'est lui que Booking stocke
comme `vehicle_id`. Une plaque déjà connue doit renvoyer le même `code`."""

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
                resp = await client.post(
                    f"{self._base_url}/api/vehicles/identify",
                    json={
                        "licensePlate": plate,
                        # Booking ne connaît pas les caractéristiques du véhicule.
                        "isElectric": False,
                        "isDisabled": False,
                        "isXl": False,
                        "isTwoWheels": False,
                    },
                )
                resp.raise_for_status()
                code = resp.json()["code"]
                if code is None:
                    raise ValueError("code absent de la réponse de Vehicles")
                return str(code)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            # Pas de plaque dans le log : donnée personnelle.
            logger.warning("Échec de l'appel à Vehicles : %s", exc)
            raise ExternalServiceError("Service Vehicles indisponible, réservation impossible") from exc
