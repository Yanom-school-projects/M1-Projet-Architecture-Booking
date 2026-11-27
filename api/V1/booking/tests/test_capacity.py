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
    CapacityService(uow).set_allocation(STD, start + timedelta(hours=1, minutes=15), 1)
    assert CapacityService(uow).check_availability(STD, start, end) == (True, 1)


def test_les_types_de_place_sont_independants(uow):
    start, end = future_slot()
    allocate(uow, PlaceType.ELECTRIC, start, end, 5)
    assert CapacityService(uow).check_availability(STD, start, end) == (False, 0)
    assert CapacityService(uow).check_availability(PlaceType.ELECTRIC, start, end) == (True, 5)


def test_reserver_consomme_une_place_par_quart_d_heure(uow):
    start, end = future_slot(hours=3)
    allocate(uow, STD, start, end, 2)
    capacity = CapacityService(uow)
    capacity.reserve(STD, start, end)
    uow.commit()
    assert booked(uow, STD, start, end) == [1] * 12
    assert capacity.check_availability(STD, start, end) == (True, 1)


def test_un_quart_d_heure_sature_bloque_tout_le_creneau_sans_reservation_partielle(uow):
    start, end = future_slot(hours=3)
    allocate(uow, STD, start, end, 1)
    CapacityService(uow).set_allocation(STD, start + timedelta(hours=2, minutes=45), 0)
    with pytest.raises(CapacityUnavailableError):
        CapacityService(uow).reserve(STD, start, end)
    uow.rollback()
    assert booked(uow, STD, start, end) == [0] * 12


def test_liberer_rend_la_place_sans_passer_sous_zero(uow):
    start, end = future_slot()
    allocate(uow, STD, start, end, 1)
    capacity = CapacityService(uow)
    capacity.reserve(STD, start, end)
    capacity.release(STD, start, end)
    capacity.release(STD, start, end)
    uow.commit()
    assert booked(uow, STD, start, end) == [0] * 8


def test_allocation_inferieure_aux_places_reservees_refusee(uow):
    start, end = future_slot(hours=1)
    allocate(uow, STD, start, end, 2)
    capacity = CapacityService(uow)
    capacity.reserve(STD, start, end)
    capacity.reserve(STD, start, end)
    with pytest.raises(CapacityBelowBookedError):
        capacity.set_allocation(STD, start, 1)
    assert capacity.set_allocation(STD, start, 2).allocated == 2


def test_allocation_hors_quart_d_heure_refusee(uow):
    start, _ = future_slot()
    with pytest.raises(InvalidSlotError):
        CapacityService(uow).set_allocation(STD, start.replace(minute=20), 3)


def test_creneaux_qui_se_touchent_partagent_la_derniere_place(uow):
    """7 h - 7 h 45 puis 7 h 45 - 9 h : aucun quart d'heure en commun, une
    seule place suffit (avec une capacité à l'heure, le second serait refusé)."""
    day, _ = future_slot(hour=7, hours=2)
    allocate(uow, STD, day, day + timedelta(hours=2), 1)
    capacity = CapacityService(uow)
    capacity.reserve(STD, day, day + timedelta(minutes=45))
    capacity.reserve(STD, day + timedelta(minutes=45), day + timedelta(hours=2))
    uow.commit()
    assert booked(uow, STD, day, day + timedelta(hours=2)) == [1] * 8
    with pytest.raises(CapacityUnavailableError):
        capacity.reserve(STD, day + timedelta(minutes=30), day + timedelta(hours=1))


def test_reservation_7h45_16h30(uow):
    start, _ = future_slot(hour=7)
    start, end = start + timedelta(minutes=45), start + timedelta(hours=9, minutes=30)
    allocate(uow, STD, start - timedelta(hours=1), end + timedelta(hours=1), 1)
    CapacityService(uow).reserve(STD, start, end)
    uow.commit()
    assert sum(booked(uow, STD, start, end)) == 35
    # Le quart d'heure avant et celui d'après restent libres.
    assert booked(uow, STD, start - timedelta(minutes=15), start) == [0]
    assert booked(uow, STD, end, end + timedelta(minutes=15)) == [0]
