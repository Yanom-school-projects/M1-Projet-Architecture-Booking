"""Faux adaptateurs pour les tests : ils implémentent les mêmes ports que les
clients HTTP réels (Vehicles, Pricing, Payment, bus d'événements), sans
réseau. C'est l'intérêt de l'architecture hexagonale : le métier se teste en
remplaçant seulement les adaptateurs.

Utilitaires de dates et de capacité partagés par les fichiers de test."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, Optional

from app.application.capacity_service import CapacityService
from app.domain.enums import PlaceType
from app.domain.exceptions import PaymentOutcomeUnknownError, PaymentRejectedError
from app.domain.rules import hour_slots
from app.domain.value_objects import PaymentAttempt, PaymentStatus, PriceQuote
from app.ports.event_publisher import EventPublisher
from app.ports.external_services import PaymentPort, PricingPort, VehiclesPort
from app.ports.metrics import BusinessMetrics

PRICE = Decimal("4.50")


class FakeVehicles(VehiclesPort):
    def __init__(self):
        self.calls: list[str] = []
        self.error: Optional[Exception] = None

    async def resolve_vehicle_id(self, plate: str) -> str:
        self.calls.append(plate)
        if self.error:
            raise self.error
        return f"veh-{plate}"


class FakePricing(PricingPort):
    def __init__(self):
        self.error: Optional[Exception] = None

    async def get_reservation_price(self, place_type: str, start_at: datetime, end_at: datetime) -> PriceQuote:
        if self.error:
            raise self.error
        return PriceQuote(amount=PRICE, reference="grille-test")


class FakePayment(PaymentPort):
    """Payment répond d'abord PENDING ; le test choisit ensuite le statut
    final avec `status`. `create_error` simule un refus ou une issue inconnue
    à la création."""

    def __init__(self):
        self.status = PaymentStatus.PENDING
        self.create_error: Optional[Exception] = None
        self.created: list[dict] = []

    async def create_payment(self, amount: Decimal, reference: str, idempotency_key: str) -> PaymentAttempt:
        self.created.append({"amount": amount, "reference": reference, "idempotency_key": idempotency_key})
        if self.create_error:
            raise self.create_error
        return PaymentAttempt(payment_id=f"pay-{reference}", status=PaymentStatus.PENDING)

    async def get_payment(self, payment_id: str) -> PaymentAttempt:
        return PaymentAttempt(payment_id=payment_id, status=self.status)


class FakeEvents(EventPublisher):
    def __init__(self):
        self.published: list[tuple[str, dict]] = []
        self.error: Optional[Exception] = None

    def publish(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self.error:
            raise self.error
        self.published.append((event_type, dict(payload)))

    def types(self) -> list[str]:
        return [event_type for event_type, _ in self.published]


class FakeMetrics(BusinessMetrics):
    def __init__(self):
        self.recorded: list[tuple[str, str]] = []

    def record(self, operation: str, result: str) -> None:
        self.recorded.append((operation, result))


class Fakes:
    def __init__(self):
        self.vehicles = FakeVehicles()
        self.pricing = FakePricing()
        self.payment = FakePayment()
        self.events = FakeEvents()
        self.metrics = FakeMetrics()


# Erreurs prêtes à l'emploi pour FakePayment.create_error.
PAYMENT_REJECTED = PaymentRejectedError("422 : demande refusée")
PAYMENT_UNKNOWN = PaymentOutcomeUnknownError("timeout")


def current_hour() -> datetime:
    return datetime.utcnow().replace(minute=0, second=0, microsecond=0)


def future_slot(days: int = 2, hour: int = 10, hours: int = 2) -> tuple[datetime, datetime]:
    """Créneau valide en UTC, `days` jours plus tard à `hour` heures pile."""
    start = (current_hour() + timedelta(days=days)).replace(hour=hour)
    return start, start + timedelta(hours=hours)


def allocate(uow, place_type: PlaceType, start: datetime, end: datetime, places: int) -> None:
    """Simule Parking : `places` places réservables sur chaque heure du créneau."""
    capacity = CapacityService(uow)
    for slot_start in hour_slots(start, end):
        capacity.set_allocation(place_type, slot_start, places)
    uow.commit()


def booked(uow, place_type: PlaceType, start: datetime, end: datetime) -> list[int]:
    """Places réservées sur chaque heure du créneau."""
    uow.session.expire_all()
    result = []
    for slot_start in hour_slots(start, end):
        slot = uow.capacity.find(place_type, slot_start)
        result.append(slot.booked if slot else 0)
    return result
