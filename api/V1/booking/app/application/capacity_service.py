"""Cas d'usage liés à la capacité réservable. Ne dépend que d'UnitOfWork
(un port) — aucune connaissance de SQLAlchemy ni de FastAPI.

Ne commite jamais lui-même : la transaction est ouverte/validée par
l'appelant (route ou ReservationService), qui peut avoir plusieurs
opérations à faire aboutir ensemble (voir application/reservation_service.py)."""

import logging
from datetime import datetime

from app.domain.enums import PlaceType
from app.domain.exceptions import CapacityBelowBookedError, CapacityUnavailableError, InvalidSlotError
from app.domain.rules import is_slot_aligned, slot_starts
from app.ports.unit_of_work import UnitOfWork

logger = logging.getLogger("booking.capacity")


class CapacityService:
    def __init__(self, uow: UnitOfWork):
        self._uow = uow

    def commit(self) -> None:
        """Exposé pour les cas d'usage à une seule étape (routes availability
        et capacity) : elles n'ont pas besoin d'orchestrer une transaction
        multi-étapes comme ReservationService, juste de valider la leur."""
        self._uow.commit()

    def check_availability(self, place_type: PlaceType, start_at: datetime, end_at: datetime) -> tuple[bool, int]:
        """Lecture seule : la capacité minimale sur les quarts d'heure du
        créneau est le facteur limitant (un seul quart d'heure saturé suffit à
        tout bloquer). Un quart d'heure que Parking n'a pas encore alloué
        compte pour 0 place."""
        existing = self._uow.capacity.find_range(place_type, start_at, end_at)
        frees = [existing[s].free if s in existing else 0 for s in slot_starts(start_at, end_at)]
        min_free = min(frees, default=0)
        return min_free > 0, min_free

    def reserve(self, place_type: PlaceType, start_at: datetime, end_at: datetime) -> None:
        """Réservation atomique sur tout le créneau : on vérifie d'abord
        chaque quart d'heure, puis on décrémente seulement si tous sont
        disponibles, pour éviter de bloquer partiellement un créneau qui
        échouera de toute façon."""
        slots = self._uow.capacity.get_range(place_type, slot_starts(start_at, end_at))
        for slot in slots:
            if slot.free <= 0:
                raise CapacityUnavailableError(place_type, slot.slot_start)
        for slot in slots:
            slot.booked += 1
        self._uow.capacity.save_many(slots)

    def release(self, place_type: PlaceType, start_at: datetime, end_at: datetime) -> None:
        """Symétrique de reserve(), utilisée quand un paiement échoue ou
        qu'une réservation est annulée."""
        slots = self._uow.capacity.get_range(place_type, slot_starts(start_at, end_at))
        for slot in slots:
            slot.booked = max(0, slot.booked - 1)
        self._uow.capacity.save_many(slots)

    def set_allocation(self, place_type: PlaceType, slot_start: datetime, allocated: int):
        """Remplace (et non additionne) la capacité allouée par Parking pour
        ce créneau ; `booked` n'est jamais touché ici pour ne pas perdre les
        réservations déjà confirmées. Refuse une allocation inférieure au
        nombre de places déjà réservées."""
        if not is_slot_aligned(slot_start):
            raise InvalidSlotError("slot_start doit tomber sur un quart d'heure (:00, :15, :30 ou :45)")
        slot = self._uow.capacity.get_or_create(place_type, slot_start)
        if allocated < slot.booked:
            raise CapacityBelowBookedError(allocated, slot.booked)
        previous = slot.allocated
        slot.allocated = allocated
        self._uow.capacity.save(slot)
        if previous != allocated:
            logger.info(
                "Capacité %s à %s modifiée : %s -> %s place(s) (%s déjà réservée(s))",
                place_type.value,
                slot_start.isoformat(),
                previous,
                allocated,
                slot.booked,
            )
        return slot
