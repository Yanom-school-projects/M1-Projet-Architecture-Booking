"""TEMPORAIRE : mode secours pour Vehicles, en attendant que le service soit
disponible. À supprimer dès que Vehicles est branché et stable.

Si Vehicles ne répond pas (URL absente, panne, erreur), Booking ne bloque
plus la réservation : il calcule lui-même un identifiant à partir de la
plaque. La plaque n'est toujours pas stockée : l'identifiant est une
empreinte HMAC-SHA256, préfixée `tmp-` pour repérer ces réservations.

Limite : cet identifiant n'est pas celui que Vehicles donnera plus tard.
Access ne retrouvera donc pas ces réservations avec un `vehicle_id` venu
de Vehicles."""

import hashlib
import hmac
import logging
import re

from app.domain.exceptions import ExternalServiceError
from app.ports.external_services import VehiclesPort

logger = logging.getLogger("booking.vehicles")

FALLBACK_PREFIX = "tmp-"


def local_vehicle_id(plate: str, secret: str) -> str:
    """Même plaque, même identifiant : « AB-123-CD », « ab 123 cd » et
    « AB123CD » donnent le même résultat."""
    normalized = re.sub(r"[^A-Z0-9]", "", plate.upper())
    digest = hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()
    return f"{FALLBACK_PREFIX}{digest[:32]}"


class FallbackVehiclesClient(VehiclesPort):
    """Essaie le vrai Vehicles, et retombe sur `local_vehicle_id` s'il échoue."""

    def __init__(self, primary: VehiclesPort, secret: str):
        self._primary = primary
        self._secret = secret

    async def resolve_vehicle_id(self, plate: str) -> str:
        try:
            return await self._primary.resolve_vehicle_id(plate)
        except ExternalServiceError as exc:
            # Pas de plaque dans le log : donnée personnelle.
            logger.warning("TEMPORAIRE : Vehicles indisponible (%s), identifiant calculé par Booking", exc)
            return local_vehicle_id(plate, self._secret)
