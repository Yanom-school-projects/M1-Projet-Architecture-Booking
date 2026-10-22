"""Cas d'usage liés à la capacité réservable. Ne dépend que d'UnitOfWork
(un port) — aucune connaissance de SQLAlchemy ni de FastAPI.

Ne commite jamais lui-même : la transaction est ouverte/validée par
l'appelant (route ou ReservationService), qui peut avoir plusieurs
opérations à faire aboutir ensemble (voir application/reservation_service.py)."""

from datetime import datetime

from app.domain.enums import PlaceType
from app.domain.exceptions import CapacityBelowBookedError, CapacityUnavailableError, InvalidSlotError
from app.domain.rules import hour_slots
from app.ports.unit_of_work import UnitOfWork


class CapacityService:
    def __init__(self, uow: UnitOfWork):
        self._uow = uow

    def commit(self) -> None:
        """Exposé pour les cas d'usage à une seule étape (routes availability
        et capacity) : elles n'ont pas besoin d'orchestrer une transaction
        multi-étapes comme ReservationService, juste de valider la leur."""
        self._uow.commit()

    def check_availability(self, place_type: PlaceType, start_at: datetime, end_at: datetime) -> tuple[bool, int]:
        """Lecture seule : la capacité minimale sur les heures du créneau est
        le facteur limitant (une seule heure saturée suffit à tout bloquer).
        Une heure que Parking n'a pas encore allouée compte pour 0 place."""
        min_free = None
        for slot_start in hour_slots(start_at, end_at):
            slot = self._uow.capacity.find(place_type, slot_start)
            free = slot.free if slot is not None else 0
            min_free = free if min_free is None else min(min_free, free)
        return (min_free is not None and min_free > 0), (min_free or 0)

    def reserve(self, place_type: PlaceType, start_at: datetime, end_at: datetime) -> None:
        """Réservation atomique sur tout le créneau : on vérifie d'abord
        chaque heure, puis on décrémente seulement si toutes sont
        disponibles, pour éviter de bloquer partiellement un créneau qui
        échouera de toute façon."""
        slots = [self._uow.capacity.get_or_create(place_type, s) for s in hour_slots(start_at, end_at)]
        for slot in slots:
            if slot.free <= 0:
                raise CapacityUnavailableError(place_type, slot.slot_start)
        for slot in slots:
            slot.booked += 1
            self._uow.capacity.save(slot)

    def release(self, place_type: PlaceType, start_at: datetime, end_at: datetime) -> None:
        """Symétrique de reserve(), utilisée quand un paiement échoue ou
        qu'une réservation est annulée."""
        for slot_start in hour_slots(start_at, end_at):
            slot = self._uow.capacity.get_or_create(place_type, slot_start)
            slot.booked = max(0, slot.booked - 1)
            self._uow.capacity.save(slot)

    def set_allocation(self, place_type: PlaceType, slot_start: datetime, allocated: int):
        """Remplace (et non additionne) la capacité allouée par Parking pour
        ce créneau ; `booked` n'est jamais touché ici pour ne pas perdre les
        réservations déjà confirmées. Refuse une allocation inférieure au
        nombre de places déjà réservées."""
        if (slot_start.minute, slot_start.second, slot_start.microsecond) != (0, 0, 0):
            raise InvalidSlotError("slot_start doit être aligné sur une heure pleine")
        slot = self._uow.capacity.get_or_create(place_type, slot_start)
        if allocated < slot.booked:
            raise CapacityBelowBookedError(allocated, slot.booked)
        slot.allocated = allocated
        self._uow.capacity.save(slot)
        return slot
