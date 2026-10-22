"""Ports vers la persistance. La couche application ne dépend que de ces
abstractions ; l'implémentation concrète (SQLAlchemy) vit dans
adapters/outbound/persistence et peut être remplacée (autre base, in-memory
pour des tests) sans toucher au métier."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.domain.entities import CapacitySlot, Reservation
from app.domain.enums import PlaceType


class ReservationRepository(ABC):
    @abstractmethod
    def get(self, reservation_id: str) -> Optional[Reservation]: ...

    @abstractmethod
    def exists(self, reservation_id: str) -> bool: ...

    @abstractmethod
    def add(self, reservation: Reservation) -> None: ...

    @abstractmethod
    def update(self, reservation: Reservation) -> None: ...

    @abstractmethod
    def delete(self, reservation_id: str) -> None: ...

    @abstractmethod
    def list_by_vehicle(self, vehicle_id: Optional[str]) -> list[Reservation]: ...


class CapacityRepository(ABC):
    @abstractmethod
    def get_or_create(self, place_type: PlaceType, slot_start: datetime) -> CapacitySlot: ...

    @abstractmethod
    def save(self, slot: CapacitySlot) -> None: ...
