"""CapacityService : places réservables par type et par heure, sur la base
SQLite de test."""

from datetime import timedelta

import pytest

from app.application.capacity_service import CapacityService
from app.domain.enums import PlaceType
from app.domain.exceptions import CapacityBelowBookedError, CapacityUnavailableError, InvalidSlotError
from tests.fakes import allocate, booked, future_slot

STD = PlaceType.STANDARD


def test_heure_jamais_allouee_compte_pour_zero(uow):
    start, end = future_slot()
    assert CapacityService(uow).check_availability(STD, start, end) == (False, 0)


def test_heure_la_plus_chargee_limite_le_creneau(uow):
    start, end = future_slot(hours=3)
    allocate(uow, STD, start, end, 3)
    CapacityService(uow).set_allocation(STD, start + timedelta(hours=1), 1)
    assert CapacityService(uow).check_availability(STD, start, end) == (True, 1)


def test_les_types_de_place_sont_independants(uow):
    start, end = future_slot()
    allocate(uow, PlaceType.ELECTRIC, start, end, 5)
    assert CapacityService(uow).check_availability(STD, start, end) == (False, 0)
    assert CapacityService(uow).check_availability(PlaceType.ELECTRIC, start, end) == (True, 5)


def test_reserver_consomme_une_place_par_heure(uow):
    start, end = future_slot(hours=3)
    allocate(uow, STD, start, end, 2)
    capacity = CapacityService(uow)
    capacity.reserve(STD, start, end)
    uow.commit()
    assert booked(uow, STD, start, end) == [1, 1, 1]
    assert capacity.check_availability(STD, start, end) == (True, 1)


def test_une_heure_saturee_bloque_tout_le_creneau_sans_reservation_partielle(uow):
    start, end = future_slot(hours=3)
    allocate(uow, STD, start, end, 1)
    CapacityService(uow).set_allocation(STD, start + timedelta(hours=2), 0)
    with pytest.raises(CapacityUnavailableError):
        CapacityService(uow).reserve(STD, start, end)
    uow.rollback()
    assert booked(uow, STD, start, end) == [0, 0, 0]


def test_liberer_rend_la_place_sans_passer_sous_zero(uow):
    start, end = future_slot()
    allocate(uow, STD, start, end, 1)
    capacity = CapacityService(uow)
    capacity.reserve(STD, start, end)
    capacity.release(STD, start, end)
    capacity.release(STD, start, end)
    uow.commit()
    assert booked(uow, STD, start, end) == [0, 0]


def test_allocation_inferieure_aux_places_reservees_refusee(uow):
    start, end = future_slot(hours=1)
    allocate(uow, STD, start, end, 2)
    capacity = CapacityService(uow)
    capacity.reserve(STD, start, end)
    capacity.reserve(STD, start, end)
    with pytest.raises(CapacityBelowBookedError):
        capacity.set_allocation(STD, start, 1)
    assert capacity.set_allocation(STD, start, 2).allocated == 2


def test_allocation_hors_heure_pleine_refusee(uow):
    start, _ = future_slot()
    with pytest.raises(InvalidSlotError):
        CapacityService(uow).set_allocation(STD, start.replace(minute=30), 3)
