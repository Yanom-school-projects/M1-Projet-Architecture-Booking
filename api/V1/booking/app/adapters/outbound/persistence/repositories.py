"""Implémentation SQLAlchemy des ports de persistance (ports/repositories.py).
Convertit entre les entités du domaine (dataclasses) et les modèles ORM."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.entities import CapacitySlot, Reservation
from app.domain.enums import PlaceType
from app.ports.repositories import CapacityRepository, ReservationRepository

from .orm_models import CapacitySlotModel, ReservationModel


def _reservation_to_domain(row: ReservationModel) -> Reservation:
    return Reservation(
        id=row.id,
        vehicle_id=row.vehicle_id,
        email=row.email,
        place_type=row.place_type,
        start_at=row.start_at,
        end_at=row.end_at,
        status=row.status,
        price_amount=row.price_amount,
        price_reference=row.price_reference,
        payment_id=row.payment_id,
        refund_amount=row.refund_amount,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _capacity_to_domain(row: CapacitySlotModel) -> CapacitySlot:
    return CapacitySlot(
        id=row.id, place_type=row.place_type, slot_start=row.slot_start, allocated=row.allocated, booked=row.booked
    )


class SqlAlchemyReservationRepository(ReservationRepository):
    def __init__(self, session: Session):
        self._session = session

    def get(self, reservation_id: str) -> Optional[Reservation]:
        row = self._session.get(ReservationModel, reservation_id)
        return _reservation_to_domain(row) if row is not None else None

    def exists(self, reservation_id: str) -> bool:
        return self._session.get(ReservationModel, reservation_id) is not None

    def add(self, reservation: Reservation) -> None:
        row = ReservationModel(
            id=reservation.id,
            vehicle_id=reservation.vehicle_id,
            email=reservation.email,
            place_type=reservation.place_type,
            start_at=reservation.start_at,
            end_at=reservation.end_at,
            status=reservation.status,
            price_amount=reservation.price_amount,
            price_reference=reservation.price_reference,
            payment_id=reservation.payment_id,
            refund_amount=reservation.refund_amount,
        )
        self._session.add(row)
        self._session.flush()
        reservation.created_at = row.created_at
        reservation.updated_at = row.updated_at

    def update(self, reservation: Reservation) -> None:
        row = self._session.get(ReservationModel, reservation.id)
        row.status = reservation.status
        row.price_amount = reservation.price_amount
        row.price_reference = reservation.price_reference
        row.payment_id = reservation.payment_id
        row.refund_amount = reservation.refund_amount
        self._session.flush()
        reservation.updated_at = row.updated_at

    def delete(self, reservation_id: str) -> None:
        row = self._session.get(ReservationModel, reservation_id)
        if row is not None:
            self._session.delete(row)

    def list_by_vehicle(self, vehicle_id: Optional[str]) -> list[Reservation]:
        query = self._session.query(ReservationModel)
        if vehicle_id:
            query = query.filter(ReservationModel.vehicle_id == vehicle_id)
        return [_reservation_to_domain(row) for row in query.all()]


class SqlAlchemyCapacityRepository(CapacityRepository):
    def __init__(self, session: Session):
        self._session = session

    def get_or_create(self, place_type: PlaceType, slot_start: datetime) -> CapacitySlot:
        """Un créneau non encore alloué par Parking vaut 0/0 par défaut
        plutôt que de lever une erreur : la disponibilité est alors
        naturellement `False`."""
        row = (
            self._session.query(CapacitySlotModel)
            .filter(CapacitySlotModel.place_type == place_type, CapacitySlotModel.slot_start == slot_start)
            .one_or_none()
        )
        if row is None:
            slot = CapacitySlot(place_type=place_type, slot_start=slot_start, allocated=0, booked=0)
            row = CapacitySlotModel(
                id=slot.id, place_type=place_type, slot_start=slot_start, allocated=0, booked=0
            )
            self._session.add(row)
            self._session.flush()
        return _capacity_to_domain(row)

    def save(self, slot: CapacitySlot) -> None:
        row = self._session.get(CapacitySlotModel, slot.id)
        row.allocated = slot.allocated
        row.booked = slot.booked
        self._session.flush()
