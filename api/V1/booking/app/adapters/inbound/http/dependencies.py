"""Composition : assemble les cas d'usage (application/) avec les
adaptateurs sortants concrets (SQLAlchemy, HTTP, RabbitMQ) à chaque requête.
C'est le seul endroit qui connaît à la fois les ports et leurs implémentations
réelles — le reste du code ne manipule que des interfaces."""

import asyncio
import logging
import time

from fastapi import Depends

from app.adapters.outbound.external_services.payment_client import HttpPaymentClient
from app.adapters.outbound.external_services.pricing_client import HttpPricingClient
from app.adapters.outbound.external_services.vehicles_client import HttpVehiclesClient
from app.adapters.outbound.external_services.vehicles_fallback import FallbackVehiclesClient
from app.adapters.outbound.messaging.event_publishers import build_event_publisher
from app.adapters.outbound.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.application.capacity_service import CapacityService
from app.application.reservation_service import ReservationService
from app.config import settings
from app.domain.enums import ReservationStatus
from app.domain.exceptions import ReservationNotFoundError
from app.ports.external_services import VehiclesPort
from app.ports.unit_of_work import UnitOfWork

logger = logging.getLogger("booking.payment_polling")

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


def build_vehicles_client() -> VehiclesPort:
    client = HttpVehiclesClient(
        settings.vehicles_service_url, api_key=settings.vehicles_api_key, timeout=settings.http_timeout_seconds
    )
    # TEMPORAIRE : mode secours tant que Vehicles n'est pas disponible.
    if settings.vehicles_fallback_enabled:
        return FallbackVehiclesClient(client, secret=settings.vehicles_fallback_secret)
    return client


def build_reservation_service(uow: UnitOfWork) -> ReservationService:
    timeout = settings.http_timeout_seconds
    return ReservationService(
        uow=uow,
        vehicles=build_vehicles_client(),
        pricing=HttpPricingClient(settings.pricing_service_url, api_key=settings.pricing_api_key, timeout=timeout),
        payment=HttpPaymentClient(settings.payment_service_url, api_key=settings.payment_api_key, timeout=timeout),
        events=_event_publisher,
        settings=settings,
    )


def get_reservation_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> ReservationService:
    return build_reservation_service(uow)


async def poll_payment_until_final(reservation_id: str) -> None:
    """Tâche de fond lancée après la création d'une réservation : interroge
    Payment à intervalle régulier jusqu'au statut final, pour que la
    réservation soit confirmée (et Messages prévenu) même si personne ne
    consulte la réservation. Une nouvelle unité de travail est ouverte à
    chaque tour, la requête HTTP d'origine étant déjà terminée."""
    deadline = time.monotonic() + settings.payment_poll_timeout_seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(settings.payment_poll_interval_seconds)
        uow = SqlAlchemyUnitOfWork()
        try:
            reservation = await build_reservation_service(uow).get_reservation(reservation_id)
            if reservation.status != ReservationStatus.PENDING_PAYMENT:
                return
        except ReservationNotFoundError:
            return
        except Exception:
            logger.exception("Erreur pendant le suivi du paiement de la réservation %s", reservation_id)
        finally:
            uow.close()
    logger.warning(
        "Paiement de la réservation %s toujours en attente après %ss ; il sera revérifié à la prochaine consultation",
        reservation_id,
        settings.payment_poll_timeout_seconds,
    )
