"""Ports vers la persistance. La couche application ne dépend que de ces
abstractions ; l'implémentation concrète (SQLAlchemy) vit dans
adapters/outbound/persistence et peut être remplacée (autre base, in-memory
pour des tests) sans toucher au métier."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.domain.entities import CapacitySlot, Reservation
from app.domain.enums import PlaceType, ReservationStatus


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
    def transition_status(
        self, reservation_id: str, from_status: ReservationStatus, to_status: ReservationStatus
    ) -> bool:
        """Change le statut seulement s'il vaut encore `from_status`, en une
        seule opération atomique. Renvoie False si quelqu'un d'autre l'a déjà
        changé : deux traitements concurrents ne peuvent pas appliquer deux
        fois la même transition."""

    @abstractmethod
    def list_by_vehicle(self, vehicle_id: Optional[str]) -> list[Reservation]: ...


class CapacityRepository(ABC):
    @abstractmethod
    def find(self, place_type: PlaceType, slot_start: datetime) -> Optional[CapacitySlot]:
        """Lecture seule : None si Parking n'a encore rien alloué."""

    @abstractmethod
    def get_or_create(self, place_type: PlaceType, slot_start: datetime) -> CapacitySlot: ...

    @abstractmethod
    def save(self, slot: CapacitySlot) -> None: ...
