"""Implémentation SQLAlchemy du port UnitOfWork : une session par unité de
travail, avec les deux repositories qui la partagent."""

from app.ports.unit_of_work import UnitOfWork

from .database import SessionLocal
from .repositories import SqlAlchemyCapacityRepository, SqlAlchemyReservationRepository


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory=SessionLocal):
        self.session = session_factory()
        self.reservations = SqlAlchemyReservationRepository(self.session)
        self.capacity = SqlAlchemyCapacityRepository(self.session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()
