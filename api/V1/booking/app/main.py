"""Point d'entrée et composition root. C'est le seul module qui assemble
concrètement l'architecture hexagonale : crée l'app FastAPI (adaptateur
entrant), monte ses routes, enregistre la traduction des exceptions
métier, et déclenche la création du schéma de persistance (adaptateur
sortant). Le câblage détaillé des cas d'usage avec leurs adaptateurs
concrets se fait requête par requête dans adapters/inbound/http/dependencies.py."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.inbound.http.exception_handlers import register_exception_handlers
from app.adapters.inbound.http.routers import availability, capacity, health, parking_sync, reservations
from app.adapters.outbound.persistence.database import Base, engine
from app.config import settings

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

API_DESCRIPTION = """
Le service **Booking** gère la disponibilité future du parking et le cycle de vie
d'une réservation : recherche de créneau, tarification, paiement anticipé et
confirmation.

### Rôle dans le système
- **Parking** indique combien de places de chaque type sont proposées à la
  réservation : Booking le lit au démarrage puis toutes les heures
  (`POST /capacity/sync` pour forcer). `PUT /capacity` permet aussi d'ajuster
  un créneau précis.
- **Vehicles** résout la plaque du client en identifiant pseudonymisé.
- **Pricing** calcule le montant d'une réservation.
- **Payment** encaisse le paiement. Il répond d'abord `PENDING` ; Booking
  l'interroge ensuite (`GET /payments/{id}`) jusqu'à `ACCEPTED` ou `REFUSED`.
- **Access** interroge Booking (`GET /reservations/active`) pour vérifier
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
    {"name": "capacity", "description": "Allocation de la capacité réservable par créneau. Appelé par le service Parking."},
]

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Synchro de capacité avec Parking en tâche de fond : le service démarre
    # sans attendre que Parking (éventuellement en veille) réponde.
    task = asyncio.create_task(parking_sync.parking_sync_loop()) if settings.parking_service_url else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    lifespan=lifespan,
    title="Booking Service",
    description=API_DESCRIPTION,
    version="0.4.0",
    openapi_tags=TAGS_METADATA,
)

register_exception_handlers(app)

app.include_router(health.router, tags=["health"])
app.include_router(availability.router, tags=["availability"])
app.include_router(reservations.router, tags=["reservations"])
app.include_router(capacity.router, tags=["capacity"])
app.include_router(parking_sync.router, tags=["capacity"])
