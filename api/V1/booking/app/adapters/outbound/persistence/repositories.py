"""Implémentation SQLAlchemy des ports de persistance (ports/repositories.py).
Convertit entre les entités du domaine (dataclasses) et les modèles ORM."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.entities import CapacitySlot, Reservation
from app.domain.enums import PlaceType, ReservationStatus
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
        correlation_id=row.correlation_id,
        payment_idempotency_key=row.payment_idempotency_key,
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
            correlation_id=reservation.correlation_id,
            payment_idempotency_key=reservation.payment_idempotency_key,
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
        self._session.flush()
        reservation.updated_at = row.updated_at

    def set_payment_id(self, reservation_id: str, payment_id: str) -> None:
        self._session.query(ReservationModel).filter(ReservationModel.id == reservation_id).update(
            {"payment_id": payment_id, "updated_at": datetime.utcnow()}, synchronize_session=False
        )

    def transition_status(
        self, reservation_id: str, from_status: ReservationStatus, to_status: ReservationStatus
    ) -> bool:
        # UPDATE ... WHERE status = from_status : la base sérialise les
        # écritures concurrentes, une seule d'entre elles modifie la ligne.
        updated = (
            self._session.query(ReservationModel)
            .filter(ReservationModel.id == reservation_id, ReservationModel.status == from_status)
            .update({"status": to_status, "updated_at": datetime.utcnow()}, synchronize_session=False)
        )
        return updated == 1

    def list_by_vehicle(self, vehicle_id: Optional[str]) -> list[Reservation]:
        query = self._session.query(ReservationModel)
        if vehicle_id:
            query = query.filter(ReservationModel.vehicle_id == vehicle_id)
        return [_reservation_to_domain(row) for row in query.all()]

    def list_covering(
        self, vehicle_id: str, at: datetime, statuses: list[ReservationStatus]
    ) -> list[Reservation]:
        rows = (
            self._session.query(ReservationModel)
            .filter(
                ReservationModel.vehicle_id == vehicle_id,
                ReservationModel.status.in_(statuses),
                ReservationModel.start_at <= at,
                ReservationModel.end_at > at,
            )
            .order_by(ReservationModel.start_at)
            .all()
        )
        return [_reservation_to_domain(row) for row in rows]


class SqlAlchemyCapacityRepository(CapacityRepository):
    def __init__(self, session: Session):
        self._session = session

    def find(self, place_type: PlaceType, slot_start: datetime) -> Optional[CapacitySlot]:
        row = (
            self._session.query(CapacitySlotModel)
            .filter(CapacitySlotModel.place_type == place_type, CapacitySlotModel.slot_start == slot_start)
            .one_or_none()
        )
        return _capacity_to_domain(row) if row is not None else None

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
        self.save_many([slot])

    def _rows_in_range(self, place_type: PlaceType, start: datetime, end: datetime) -> list[CapacitySlotModel]:
        return (
            self._session.query(CapacitySlotModel)
            .filter(
                CapacitySlotModel.place_type == place_type,
                CapacitySlotModel.slot_start >= start,
                CapacitySlotModel.slot_start < end,
            )
            .all()
        )

    def find_range(self, place_type: PlaceType, start: datetime, end: datetime) -> dict[datetime, CapacitySlot]:
        return {row.slot_start: _capacity_to_domain(row) for row in self._rows_in_range(place_type, start, end)}

    def get_range(self, place_type: PlaceType, slot_starts: list[datetime]) -> list[CapacitySlot]:
        """Une requête pour lire tout le créneau, une écriture groupée pour
        créer les quarts d'heure manquants : une réservation de 7 jours
        touche 672 quarts d'heure, la synchro Parking plus de 3 500 par type."""
        if not slot_starts:
            return []
        rows = self._rows_in_range(place_type, min(slot_starts), max(slot_starts) + timedelta(seconds=1))
        existing = {row.slot_start: row for row in rows}
        missing = [
            CapacitySlotModel(
                id=CapacitySlot(place_type=place_type, slot_start=s).id,
                place_type=place_type,
                slot_start=s,
                allocated=0,
                booked=0,
            )
            for s in slot_starts
            if s not in existing
        ]
        if missing:
            self._session.add_all(missing)
            self._session.flush()
            existing.update({row.slot_start: row for row in missing})
        return [_capacity_to_domain(existing[s]) for s in slot_starts]

    def save_many(self, slots: list[CapacitySlot]) -> None:
        for slot in slots:
            # Déjà chargées dans la session : get() ne refait pas de requête.
            row = self._session.get(CapacitySlotModel, slot.id)
            row.allocated = slot.allocated
            row.booked = slot.booked
        self._session.flush()
