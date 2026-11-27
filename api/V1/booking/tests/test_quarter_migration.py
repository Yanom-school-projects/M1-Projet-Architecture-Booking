"""Passage de la capacité à l'heure au quart d'heure (v2.7.0) : migration
des créneaux existants au démarrage, et synchronisation Parking au quart d'heure."""

import asyncio
from datetime import timedelta

from app.adapters.outbound.persistence.database import engine
from app.adapters.outbound.persistence.migrations import split_hourly_capacity
from app.application.parking_sync_service import ParkingSyncService
from app.domain.enums import PlaceType
from app.ports.parking import ParkingPort
from tests.fakes import booked, current_hour, future_slot

STD = PlaceType.STANDARD


def hourly_row(uow, place_type, slot_start, allocated, booked_places):
    """Créneau d'une heure tel que l'écrivait la v2.6.0 (ligne à hh:00)."""
    [slot] = uow.capacity.get_range(place_type, [slot_start])
    slot.allocated, slot.booked = allocated, booked_places
    uow.capacity.save(slot)
    uow.commit()


def test_chaque_heure_recoit_ses_trois_quarts_d_heure(uow):
    start, _ = future_slot(hour=10)
    hourly_row(uow, STD, start, allocated=10, booked_places=2)
    hourly_row(uow, PlaceType.XL, start, allocated=3, booked_places=0)

    created = split_hourly_capacity(engine, now=current_hour())

    assert created == 6
    uow.session.expire_all()
    quarters = uow.capacity.find_range(STD, start, start + timedelta(hours=1))
    assert sorted(quarters) == [start + timedelta(minutes=m) for m in (0, 15, 30, 45)]
    # Même allocation, mêmes places réservées : les anciennes réservations
    # tombaient sur des heures pleines, elles occupent les quatre quarts d'heure.
    assert {(slot.allocated, slot.booked) for slot in quarters.values()} == {(10, 2)}


def test_migration_jouee_une_seule_fois(uow):
    start, _ = future_slot(hour=10)
    hourly_row(uow, STD, start, allocated=10, booked_places=0)
    assert split_hourly_capacity(engine, now=current_hour()) == 3
    assert split_hourly_capacity(engine, now=current_hour()) == 0


def test_rien_a_faire_si_le_calendrier_est_deja_au_quart_d_heure(uow):
    start, _ = future_slot(hour=10)
    hourly_row(uow, STD, start, allocated=10, booked_places=0)
    hourly_row(uow, STD, start + timedelta(minutes=15), allocated=4, booked_places=0)
    assert split_hourly_capacity(engine, now=current_hour()) == 0


def test_les_creneaux_passes_ne_sont_pas_migres(uow):
    past = current_hour() - timedelta(hours=2)
    hourly_row(uow, STD, past, allocated=10, booked_places=0)
    assert split_hourly_capacity(engine, now=current_hour()) == 0


class FixedParking(ParkingPort):
    def __init__(self, places: int):
        self.places = places

    async def get_booking_capacity(self, place_type: PlaceType) -> int:
        return self.places


def test_synchro_parking_au_quart_d_heure(uow):
    now = current_hour() + timedelta(minutes=20)  # 20 min après l'heure : début au quart de 15 min
    summary = asyncio.run(ParkingSyncService(uow, FixedParking(3)).sync(now, hours=2))

    start = current_hour() + timedelta(minutes=15)
    slots = uow.capacity.find_range(STD, start, start + timedelta(hours=2))
    assert len(slots) == 8
    assert {slot.allocated for slot in slots.values()} == {3}
    assert summary["STANDARD"] == {"allocated": 3, "slots_kept_for_bookings": 0}


def test_synchro_ne_descend_pas_sous_les_places_reservees(uow):
    now = current_hour()
    asyncio.run(ParkingSyncService(uow, FixedParking(2)).sync(now, hours=1))
    [slot] = uow.capacity.get_range(STD, [now + timedelta(minutes=30)])
    slot.booked = 2
    uow.capacity.save(slot)
    uow.commit()

    summary = asyncio.run(ParkingSyncService(uow, FixedParking(1)).sync(now, hours=1))

    assert summary["STANDARD"]["slots_kept_for_bookings"] == 1
    assert booked(uow, STD, now, now + timedelta(hours=1)) == [0, 0, 2, 0]
    allocated = {s: slot.allocated for s, slot in uow.capacity.find_range(STD, now, now + timedelta(hours=1)).items()}
    assert sorted(allocated.values()) == [1, 1, 1, 2]
