"""Authentification des appels entrants par une clé d'API unique.

Toutes les routes métier et /metrics exigent la clé `API_KEY` (variable
d'environnement, jamais dans Git). Elle est partagée avec les appelants de
Booking : le front, Access et Prometheus. Seul /health reste public (health
check de Render), avec la documentation Swagger.

La clé s'envoie dans l'en-tête `X-API-Key`. Pour /metrics, l'en-tête
`Authorization: Bearer <clé>` est aussi accepté : c'est le format que
Prometheus sait envoyer.

Sans API_KEY configurée, toutes les routes protégées refusent les appels
(le service échoue fermé plutôt que de s'ouvrir par oubli)."""

import hmac
import logging
from typing import Optional

from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

logger = logging.getLogger("booking.security")

# auto_error=False : on renvoie nous-mêmes un 401 propre (FastAPI renverrait 403).
# Déclaré via Security : Swagger affiche le bouton « Authorize ».
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Clé d'API de Booking.")

# Réponse ajoutée à la documentation de chaque route protégée.
AUTH_RESPONSES = {401: {"description": "Clé d'API absente ou invalide (en-tête `X-API-Key`)."}}


def is_valid_key(received: Optional[str]) -> bool:
    """Comparaison en temps constant (le temps de réponse ne dit pas combien de
    caractères sont justes), en octets pour accepter tout caractère reçu."""
    expected = settings.api_key
    if not expected or not received:
        return False
    return hmac.compare_digest(received.encode(), expected.encode())


def _reject(received: Optional[str]) -> HTTPException:
    # Jamais la clé reçue dans le log : seulement le fait qu'elle manque.
    logger.warning("Accès refusé : clé d'API %s", "absente" if not received else "invalide")
    return HTTPException(
        status_code=401, detail="Clé d'API absente ou invalide", headers={"WWW-Authenticate": "ApiKey"}
    )


def require_api_key(api_key: Optional[str] = Security(_api_key_header)) -> None:
    """Dépendance posée sur les routeurs métier (voir app/main.py)."""
    if not is_valid_key(api_key):
        raise _reject(api_key)


def require_api_key_or_bearer(
    api_key: Optional[str] = Security(_api_key_header),
    authorization: Optional[str] = Header(None),
) -> None:
    """Pour /metrics : même clé, en X-API-Key ou en Bearer (Prometheus)."""
    scheme, _, token = (authorization or "").partition(" ")
    bearer = token.strip() if scheme.lower() == "bearer" else None
    if not (is_valid_key(api_key) or is_valid_key(bearer)):
        raise _reject(api_key or bearer)
