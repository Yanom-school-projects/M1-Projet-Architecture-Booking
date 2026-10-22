"""Synchronisation de la capacité depuis Parking : route manuelle et tâche
périodique lancée au démarrage du service (voir app/main.py)."""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.adapters.outbound.external_services.parking_client import HttpParkingClient
from app.adapters.outbound.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.application.parking_sync_service import ParkingSyncService
from app.config import settings

logger = logging.getLogger("booking.parking_sync")
router = APIRouter()


def _sync_hours() -> int:
    # Une réservation peut commencer jusqu'à l'horizon et durer la durée max.
    return settings.reservation_horizon_days * 24 + settings.reservation_max_duration_hours


async def run_parking_sync() -> dict:
    uow = SqlAlchemyUnitOfWork()
    try:
        parking = HttpParkingClient(
            settings.parking_service_url, api_key=settings.parking_api_key, timeout=settings.http_timeout_seconds
        )
        return await ParkingSyncService(uow, parking).sync(datetime.utcnow(), _sync_hours())
    finally:
        uow.close()


async def parking_sync_loop() -> None:
    """Synchronise au démarrage puis à intervalle régulier : ajoute les
    nouvelles heures réservables au fil des jours et suit les changements
    d'offre de Parking. Sur Render (plan gratuit), la base est vidée à chaque
    redémarrage : cette synchro la remplit à nouveau automatiquement."""
    while True:
        try:
            await run_parking_sync()
        except Exception:
            logger.exception("Échec de la synchronisation de capacité avec Parking")
        await asyncio.sleep(settings.parking_sync_interval_seconds)


@router.post(
    "/capacity/sync",
    summary="Synchroniser la capacité réservable depuis Parking",
    response_description="Nombre de places appliqué par type de place.",
    responses={503: {"description": "PARKING_SERVICE_URL n'est pas configurée."}},
)
async def sync_capacity():
    """Demande à **Parking** combien de places de chaque type sont proposées
    à la réservation, et applique ce nombre à chaque heure des 30 prochains
    jours (+ 7 jours, durée maximale d'une réservation).

    Une heure n'est jamais ramenée sous le nombre de places déjà réservées.
    Lancé aussi automatiquement au démarrage puis toutes les heures.
    """
    if not settings.parking_service_url:
        raise HTTPException(503, "PARKING_SERVICE_URL n'est pas configurée")
    return await run_parking_sync()
