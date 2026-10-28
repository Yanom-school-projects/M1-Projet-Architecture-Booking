"""Ports vers les services externes dont Booking dépend de façon
synchrone : Vehicles (résolution de plaque), Pricing (tarification),
Payment (paiement). Chaque implémentation concrète (adapters/outbound/
external_services) parle HTTP ; la couche application ne le sait pas."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from app.domain.value_objects import PaymentAttempt, PriceQuote


class VehiclesPort(ABC):
    @abstractmethod
    async def resolve_vehicle_id(self, plate: str) -> str: ...


class PricingPort(ABC):
    async def wake_up(self) -> None:
        """Réveille le service s'il est en veille. Ne fait rien par défaut."""

    @abstractmethod
    async def get_reservation_price(self, place_type: str, start_at: datetime, end_at: datetime) -> PriceQuote: ...


class PaymentPort(ABC):
    async def wake_up(self) -> None:
        """Réveille le service s'il est en veille. Ne fait rien par défaut."""

    @abstractmethod
    async def create_payment(self, amount: Decimal, reference: str, idempotency_key: str) -> PaymentAttempt: ...

    @abstractmethod
    async def get_payment(self, payment_id: str) -> PaymentAttempt: ...
