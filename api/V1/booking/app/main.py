"""Point d'entrée et composition root. C'est le seul module qui assemble
concrètement l'architecture hexagonale : crée l'app FastAPI (adaptateur
entrant), monte ses routes, enregistre la traduction des exceptions
métier, et déclenche la création du schéma de persistance (adaptateur
sortant). Le câblage détaillé des cas d'usage avec leurs adaptateurs
concrets se fait requête par requête dans adapters/inbound/http/dependencies.py."""

import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI

from app.adapters.inbound.http.correlation_middleware import CorrelationIdMiddleware
from app.adapters.inbound.http.exception_handlers import register_exception_handlers
from app.adapters.inbound.http.routers import availability, capacity, health, parking_sync, reservations
from app.adapters.outbound.persistence.database import Base, engine
from app.adapters.outbound.persistence.migrations import add_missing_columns
from app.config import settings
from app.logging_config import setup_logging

setup_logging()

Base.metadata.create_all(bind=engine)
add_missing_columns(engine)

API_DESCRIPTION = """
Le service **Booking** gère la disponibilité future du parking et le cycle de vie
d'une réservation : recherche de créneau, tarification, paiement anticipé et
confirmation.

Toutes les routes sont préfixées par `/v2/booking` (ex. `POST /v2/booking/reservations`).

### Rôle dans le système
- **Parking** indique combien de places de chaque type sont proposées à la
  réservation : Booking le lit au démarrage puis toutes les heures
  (`POST /capacity-slots/sync` pour forcer). `PUT /capacity-slots/{type}/{heure}` permet aussi d'ajuster
  un créneau précis.
- **Vehicles** résout la plaque du client en identifiant pseudonymisé.
- **Pricing** calcule le montant d'une réservation.
- **Payment** encaisse le paiement. Il répond d'abord `PENDING` ; Booking
  l'interroge ensuite (`GET /payments/{id}`) jusqu'à `ACCEPTED` ou `REFUSED`.
- **Access** interroge Booking (`GET /reservations/valid`) pour vérifier
  qu'un véhicule qui se présente possède une réservation valable maintenant.
- **Messages** reçoit les événements `reservation.confirmed` et
  `reservation.cancelled` pour générer les confirmations/reçus client.

### Cycle de vie d'une réservation
`pending_payment` → `confirmed` (paiement accepté) ou `failed` (paiement
refusé). Une réservation `confirmed` peut être annulée par le client
(`POST /reservations/{id}/cancel`) : elle passe à `cancelled` et la place est
libérée, **sans remboursement** (Payment ne gère pas les remboursements).

### Architecture
Ce service suit une architecture hexagonale (ports & adapters) : voir
`docs/booking_architecture.md` pour le détail des couches (domain / ports /
application / adapters).
"""

TAGS_METADATA = [
    {"name": "health", "description": "Supervision : vérifie que le service répond."},
    {"name": "availability", "description": "Consultation de la capacité réservable, sans effet de bord métier."},
    {"name": "reservations", "description": "Création et consultation des réservations d'une place de parking."},
    {"name": "capacity", "description": "Places réservables par créneau horaire : synchronisation depuis Parking et ajustement d'un créneau."},
]

logger = logging.getLogger("booking.startup")


def _host(url: str) -> str:
    """Hôte seul : jamais d'identifiants (ex. CLOUDAMQP_URL contient le mot de passe)."""
    return (urlsplit(url).hostname or "?") if url else "non configuré"


def _log_startup_config() -> None:
    logger.info(
        "Booking %s démarré : vehicles=%s pricing=%s payment=%s parking=%s bus=%s base=%s logs=%s",
        app.version,
        _host(settings.vehicles_service_url),
        _host(settings.pricing_service_url),
        _host(settings.payment_service_url),
        _host(settings.parking_service_url),
        _host(settings.cloudamqp_url),
        settings.database_url.split(":", 1)[0],
        settings.log_dir or "console uniquement",
    )
    if not settings.cloudamqp_url:
        logger.warning("CLOUDAMQP_URL vide : les événements ne sont PAS envoyés à Messages, seulement logués")
    if not settings.parking_service_url:
        logger.warning("PARKING_SERVICE_URL vide : pas de synchro de capacité, seul PUT /capacity-slots l'alimente")
    if settings.vehicles_fallback_enabled:
        logger.warning("TEMPORAIRE : secours Vehicles activé, identifiants calculés par Booking si Vehicles tombe")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _log_startup_config()
    # Synchro de capacité avec Parking en tâche de fond : le service démarre
    # sans attendre que Parking (éventuellement en veille) réponde.
    task = asyncio.create_task(parking_sync.parking_sync_loop()) if settings.parking_service_url else None
    yield
    if task:
        task.cancel()


# Préfixe commun à toutes les routes : /v2/booking/... (version de l'API, puis
# nom du service, pour un routage par préfixe devant les services).
API_PREFIX = "/v2/booking"

app = FastAPI(
    lifespan=lifespan,
    title="Booking Service",
    description=API_DESCRIPTION,
    version="0.4.0",
    openapi_tags=TAGS_METADATA,
)

register_exception_handlers(app)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(health.router, prefix=API_PREFIX, tags=["health"])
app.include_router(availability.router, prefix=API_PREFIX, tags=["availability"])
app.include_router(reservations.router, prefix=API_PREFIX, tags=["reservations"])
app.include_router(capacity.router, prefix=API_PREFIX, tags=["capacity"])
app.include_router(parking_sync.router, prefix=API_PREFIX, tags=["capacity"])
