"""Point d'entrée et composition root. C'est le seul module qui assemble
concrètement l'architecture hexagonale : crée l'app FastAPI (adaptateur
entrant), monte ses routes, enregistre la traduction des exceptions
métier, et déclenche la création du schéma de persistance (adaptateur
sortant). Le câblage détaillé des cas d'usage avec leurs adaptateurs
concrets se fait requête par requête dans adapters/inbound/http/dependencies.py."""

import logging

from fastapi import FastAPI

from app.adapters.inbound.http.exception_handlers import register_exception_handlers
from app.adapters.inbound.http.routers import availability, capacity, health, reservations
from app.adapters.outbound.persistence.database import Base, engine

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

API_DESCRIPTION = """
Le service **Booking** gère la disponibilité future du parking et le cycle de vie
d'une réservation : recherche de créneau, tarification, paiement anticipé et
confirmation.

### Rôle dans le système
- **Parking** alloue à Booking un nombre de places réservables par type et par
  créneau horaire (`PUT /capacity`).
- **Vehicles** résout la plaque du client en identifiant pseudonymisé.
- **Pricing** calcule le montant d'une réservation.
- **Payment** encaisse le paiement. Il répond d'abord `PENDING` ; Booking
  l'interroge ensuite (`GET /payments/{id}`) jusqu'à `ACCEPTED` ou `REFUSED`.
- **Access** interroge Booking pour vérifier qu'un véhicule qui se présente
  possède une réservation valable.
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

app = FastAPI(
    title="Booking Service",
    description=API_DESCRIPTION,
    version="0.2.0",
    openapi_tags=TAGS_METADATA,
)

register_exception_handlers(app)

app.include_router(health.router, tags=["health"])
app.include_router(availability.router, tags=["availability"])
app.include_router(reservations.router, tags=["reservations"])
app.include_router(capacity.router, tags=["capacity"])
