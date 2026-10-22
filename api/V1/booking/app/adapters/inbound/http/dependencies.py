"""Composition : assemble les cas d'usage (application/) avec les
adaptateurs sortants concrets (SQLAlchemy, HTTP, RabbitMQ) à chaque requête.
C'est le seul endroit qui connaît à la fois les ports et leurs implémentations
réelles — le reste du code ne manipule que des interfaces."""

from fastapi import Depends

from app.adapters.outbound.external_services.payment_client import HttpPaymentClient
from app.adapters.outbound.external_services.pricing_client import HttpPricingClient
from app.adapters.outbound.external_services.vehicles_client import HttpVehiclesClient
from app.adapters.outbound.messaging.event_publishers import build_event_publisher
from app.adapters.outbound.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.application.capacity_service import CapacityService
from app.application.reservation_service import ReservationService
from app.config import settings
from app.ports.unit_of_work import UnitOfWork

# Un seul publisher pour la vie du process : une connexion AMQP est ouverte/
# fermée à chaque publish() (voir event_publishers.py), pas besoin de recréer
# l'objet Python à chaque requête.
_event_publisher = build_event_publisher(settings.cloudamqp_url, settings.event_bus_exchange)


def get_unit_of_work():
    uow = SqlAlchemyUnitOfWork()
    try:
        yield uow
    finally:
        uow.close()


def get_capacity_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> CapacityService:
    return CapacityService(uow)


def get_reservation_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> ReservationService:
    return ReservationService(
        uow=uow,
        vehicles=HttpVehiclesClient(settings.vehicles_service_url),
        pricing=HttpPricingClient(settings.pricing_service_url),
        payment=HttpPaymentClient(settings.payment_service_url),
        events=_event_publisher,
        settings=settings,
    )
