"""Unit of Work : regroupe les repositories d'une même transaction, pour que
la couche application puisse valider (commit) ou annuler (rollback)
plusieurs écritures ensemble sans connaître la technologie de persistance."""

from abc import ABC, abstractmethod

from app.ports.repositories import CapacityRepository, ReservationRepository


class UnitOfWork(ABC):
    reservations: ReservationRepository
    capacity: CapacityRepository

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is not None:
            self.rollback()

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...
