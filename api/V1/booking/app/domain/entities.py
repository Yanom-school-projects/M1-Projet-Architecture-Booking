"""Entités métier : objets Python purs (dataclasses), sans dépendance à
SQLAlchemy, FastAPI ou tout autre framework. C'est le cœur de l'hexagone —
rien ici ne sait qu'il existe une base de données ou une API HTTP. Les
adaptateurs de persistance (adapters/outbound/persistence) savent convertir
entre ces entités et leurs propres modèles de stockage, jamais l'inverse."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .enums import PlaceType, ReservationStatus


@dataclass
class Reservation:
    id: str
    vehicle_id: str
    email: str
    place_type: PlaceType
    start_at: datetime
    end_at: datetime
    status: ReservationStatus = ReservationStatus.PENDING_PAYMENT
    price_amount: Optional[Decimal] = None
    price_reference: Optional[str] = None
    payment_id: Optional[str] = None
    refund_amount: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class CapacitySlot:
    """Nombre de places réservables par type et par heure pleine — pas
    d'affectation nominale d'une place précise, conformément au cadrage
    métier (le parking gère un stock, pas des places numérotées)."""

    place_type: PlaceType
    slot_start: datetime
    allocated: int = 0
    booked: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def free(self) -> int:
        return self.allocated - self.booked
