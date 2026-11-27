"""Parcours d'une réservation (ReservationService) avec de faux Vehicles,
Pricing, Payment et bus d'événements : création, paiement accepté ou refusé,
pannes des services, annulation."""

import asyncio

import pytest

from app.domain.enums import PlaceType, ReservationStatus
from app.domain.exceptions import (
    CapacityUnavailableError,
    ExternalServiceError,
    InvalidReservationStateError,
    ReservationNotFoundError,
)
from app.domain.value_objects import PaymentStatus
from app.ports.metrics import Operation, Result
from tests.fakes import PAYMENT_REJECTED, PAYMENT_UNKNOWN, PRICE, allocate, booked, future_slot

STD = PlaceType.STANDARD
PLATE = "AB-123-CD"


def create(service, start, end, place_type=STD):
    return asyncio.run(service.create_reservation(PLATE, "client@example.com", place_type, start, end))


@pytest.fixture
def slot(uow):
    start, end = future_slot()
    allocate(uow, STD, start, end, 1)
    return start, end


def test_creation_en_attente_de_paiement(service, fakes, uow, slot):
    reservation = create(service, *slot)

    assert reservation.status == ReservationStatus.PENDING_PAYMENT
    assert len(reservation.id) == 6 and reservation.id.isdigit()
    assert reservation.vehicle_id == f"veh-{PLATE}"
    assert reservation.price_amount == PRICE
    assert reservation.payment_id == f"pay-{reservation.id}"
    assert booked(uow, STD, *slot) == [1] * 8
    assert fakes.payment.created[0]["idempotency_key"] == f"booking:{reservation.id}:create"
    assert (Operation.RESERVATION_CREATE, Result.SUCCESS) in fakes.metrics.recorded


def test_la_plaque_n_est_jamais_stockee(service, uow, slot):
    reservation = create(service, *slot)
    stored = uow.reservations.get(reservation.id)
    assert PLATE not in (stored.vehicle_id, stored.email)


def test_paiement_accepte_confirme_et_previent_messages(service, fakes, slot):
    reservation = create(service, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED

    confirmed = asyncio.run(service.get_reservation(reservation.id))

    assert confirmed.status == ReservationStatus.CONFIRMED
    assert fakes.events.types() == ["reservation.confirmed"]
    payload = fakes.events.published[0][1]
    assert payload["reservation_id"] == reservation.id
    assert payload["place_type"] == "STANDARD"
    assert (Operation.RESERVATION_PAYMENT, Result.ACCEPTED) in fakes.metrics.recorded


def test_confirmation_idempotente_un_seul_evenement(service, fakes, slot):
    reservation = create(service, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED
    asyncio.run(service.get_reservation(reservation.id))
    asyncio.run(service.get_reservation(reservation.id))
    assert fakes.events.types() == ["reservation.confirmed"]


def test_paiement_refuse_libere_la_place(service, fakes, uow, slot):
    reservation = create(service, *slot)
    fakes.payment.status = PaymentStatus.REFUSED

    failed = asyncio.run(service.get_reservation(reservation.id))

    assert failed.status == ReservationStatus.FAILED
    assert booked(uow, STD, *slot) == [0] * 8
    assert fakes.events.published == []


def test_paiement_en_attente_ne_change_rien(service, fakes, uow, slot):
    reservation = create(service, *slot)
    pending = asyncio.run(service.get_reservation(reservation.id))
    assert pending.status == ReservationStatus.PENDING_PAYMENT
    assert booked(uow, STD, *slot) == [1] * 8


def test_plus_de_place_refuse_sans_appeler_vehicles(service, fakes, slot):
    create(service, *slot)  # prend la seule place
    with pytest.raises(CapacityUnavailableError):
        create(service, *slot)
    assert len(fakes.vehicles.calls) == 1
    assert (Operation.RESERVATION_CREATE, Result.ERROR) in fakes.metrics.recorded


def test_vehicles_en_panne_ne_consomme_pas_de_place(service, fakes, uow, slot):
    fakes.vehicles.error = ExternalServiceError("Vehicles injoignable")
    with pytest.raises(ExternalServiceError):
        create(service, *slot)
    assert booked(uow, STD, *slot) == [0] * 8
    assert uow.reservations.list_by_vehicle(None) == []


def test_pricing_en_panne_reservation_en_echec_et_place_liberee(service, fakes, uow, slot):
    fakes.pricing.error = RuntimeError("Pricing injoignable")
    with pytest.raises(ExternalServiceError):
        create(service, *slot)
    [reservation] = uow.reservations.list_by_vehicle(None)
    assert reservation.status == ReservationStatus.FAILED
    assert booked(uow, STD, *slot) == [0] * 8
    assert fakes.payment.created == []


def test_paiement_refuse_a_la_creation(service, fakes, uow, slot):
    fakes.payment.create_error = PAYMENT_REJECTED
    with pytest.raises(ExternalServiceError):
        create(service, *slot)
    [reservation] = uow.reservations.list_by_vehicle(None)
    assert reservation.status == ReservationStatus.FAILED
    assert booked(uow, STD, *slot) == [0] * 8


def test_issue_du_paiement_inconnue_renvoyee_avec_la_meme_cle(service, fakes, uow, slot):
    fakes.payment.create_error = PAYMENT_UNKNOWN
    reservation = create(service, *slot)
    assert reservation.status == ReservationStatus.PENDING_PAYMENT
    assert reservation.payment_id is None

    # Payment répond de nouveau : la demande est renvoyée à la consultation.
    fakes.payment.create_error = None
    fakes.payment.status = PaymentStatus.ACCEPTED
    confirmed = asyncio.run(service.get_reservation(reservation.id))

    assert confirmed.status == ReservationStatus.CONFIRMED
    keys = {call["idempotency_key"] for call in fakes.payment.created}
    assert keys == {f"booking:{reservation.id}:create"}
    assert len(fakes.payment.created) == 2


def test_bus_en_panne_n_empeche_pas_la_confirmation(service, fakes, slot):
    reservation = create(service, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED
    fakes.events.error = ConnectionError("RabbitMQ injoignable")
    confirmed = asyncio.run(service.get_reservation(reservation.id))
    assert confirmed.status == ReservationStatus.CONFIRMED


def test_annulation_libere_la_place_et_previent_messages(service, fakes, uow, slot):
    reservation = create(service, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED
    asyncio.run(service.get_reservation(reservation.id))

    cancelled = service.cancel_reservation(reservation.id)

    assert cancelled.status == ReservationStatus.CANCELLED
    assert booked(uow, STD, *slot) == [0] * 8
    assert fakes.events.types() == ["reservation.confirmed", "reservation.cancelled"]


def test_annuler_une_reservation_non_confirmee_refuse(service, slot):
    reservation = create(service, *slot)
    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation.id)


def test_annuler_deux_fois_refuse(service, fakes, slot):
    reservation = create(service, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED
    asyncio.run(service.get_reservation(reservation.id))
    service.cancel_reservation(reservation.id)
    with pytest.raises(InvalidReservationStateError):
        service.cancel_reservation(reservation.id)


def test_reservation_inconnue(service):
    with pytest.raises(ReservationNotFoundError):
        asyncio.run(service.get_reservation("000000"))
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("000000")
