"""Synchronisation de la capacité réservable depuis le service Parking.

Parking ne pousse pas la capacité vers Booking (PUT /capacity) : c'est
Booking qui lui demande, pour chaque type de place, combien de places sont
proposées à la réservation, puis applique ce nombre à chaque quart d'heure
de son calendrier (horizon de réservation + durée maximale d'une réservation).

Un quart d'heure n'est jamais ramené sous le nombre de places déjà réservées :
les réservations confirmées restent honorées si Parking réduit son offre."""

import logging
from datetime import datetime, timedelta

from app.domain.enums import PlaceType
from app.domain.rules import slot_floor, slot_starts
from app.ports.parking import ParkingPort
from app.ports.unit_of_work import UnitOfWork

logger = logging.getLogger("booking.parking_sync")


class ParkingSyncService:
    def __init__(self, uow: UnitOfWork, parking: ParkingPort):
        self._uow = uow
        self._parking = parking

    async def sync(self, now: datetime, hours: int) -> dict:
        start = slot_floor(now)
        quarters = slot_starts(start, start + timedelta(hours=hours))
        summary: dict = {}
        for place_type in PlaceType:
            try:
                allocated = await self._parking.get_booking_capacity(place_type)
            except Exception as exc:
                logger.warning("Capacité Parking indisponible pour %s : %r", place_type.value, exc)
                summary[place_type.value] = {"error": "Parking injoignable ou catégorie inconnue"}
                continue

            # Lecture et création groupées : plus de 3 500 quarts d'heure par type.
            slots = self._uow.capacity.get_range(place_type, quarters)
            changed = []
            kept_for_bookings = 0
            for slot in slots:
                target = max(allocated, slot.booked)
                if target != allocated:
                    kept_for_bookings += 1
                if slot.allocated != target:
                    slot.allocated = target
                    changed.append(slot)
            self._uow.capacity.save_many(changed)
            self._uow.commit()

            summary[place_type.value] = {"allocated": allocated, "slots_kept_for_bookings": kept_for_bookings}
            logger.info(
                "Capacité %s synchronisée depuis Parking : %s place(s) sur %sh", place_type.value, allocated, hours
            )
        return summary
