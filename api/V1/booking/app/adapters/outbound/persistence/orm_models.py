"""Modèles ORM (tables SQLAlchemy) : la représentation en base des entités
du domaine. Volontairement séparés de app/domain/entities.py — le domaine ne
doit rien savoir de la persistance ; c'est ce module (et repositories.py,
qui convertit dans les deux sens) qui porte cette connaissance."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, Numeric, String, UniqueConstraint

from app.domain.enums import PlaceType, ReservationStatus

from .database import Base


def _enum_column(enum_cls):
    # Stocke la value ("standard") plutôt que le name Python ("STANDARD"),
    # pour que le contenu de la base reste lisible tel quel.
    return Enum(enum_cls, values_callable=lambda e: [member.value for member in e])


class CapacitySlotModel(Base):
    __tablename__ = "capacity_slots"
    __table_args__ = (UniqueConstraint("place_type", "slot_start", name="uq_capacity_slot"),)

    id = Column(String, primary_key=True)
    place_type = Column(_enum_column(PlaceType), nullable=False)
    slot_start = Column(DateTime, nullable=False)
    allocated = Column(Integer, nullable=False, default=0)
    booked = Column(Integer, nullable=False, default=0)


class ReservationModel(Base):
    __tablename__ = "reservations"

    id = Column(String(6), primary_key=True)
    vehicle_id = Column(String, nullable=False, index=True)
    email = Column(String, nullable=False)
    place_type = Column(_enum_column(PlaceType), nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    status = Column(_enum_column(ReservationStatus), nullable=False, default=ReservationStatus.PENDING_PAYMENT)
    price_amount = Column(Numeric(10, 2), nullable=True)
    price_reference = Column(String, nullable=True)
    payment_id = Column(String, nullable=True, index=True)
    refund_amount = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
