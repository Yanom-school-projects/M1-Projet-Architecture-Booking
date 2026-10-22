from datetime import datetime

from fastapi import APIRouter, Depends

from app.application.capacity_service import CapacityService
from app.config import settings
from app.domain.enums import PlaceType
from app.domain.rules import validate_slot

from ..dependencies import get_capacity_service
from ..schemas import AvailabilityResponse, to_utc_naive

router = APIRouter()


@router.get(
    "/availability",
    summary="Consulter la capacité disponible sur un créneau",
    response_model=AvailabilityResponse,
    response_description="Disponibilité et capacité minimale libre sur le créneau demandé.",
    responses={422: {"description": "Créneau invalide (non aligné sur une heure pleine, passé, ou trop long/lointain)."}},
)
def get_availability(
    place_type: PlaceType,
    start_at: datetime,
    end_at: datetime,
    capacity_service: CapacityService = Depends(get_capacity_service),
):
    """Répond à la question « pour ce type de place, entre `start_at` et
    `end_at`, reste-t-il une capacité disponible ? ».

    Le créneau est découpé en heures pleines ; la disponibilité renvoyée est
    celle de l'heure la plus chargée du créneau (le facteur limitant). Cette
    lecture n'a aucun effet sur la capacité : elle ne réserve rien.

    Les mêmes règles de créneau que pour une réservation s'appliquent. Les
    dates sans fuseau sont lues comme de l'UTC.
    """
    start_at, end_at = to_utc_naive(start_at), to_utc_naive(end_at)
    validate_slot(
        start_at,
        end_at,
        now=datetime.utcnow(),
        horizon_days=settings.reservation_horizon_days,
        max_duration_hours=settings.reservation_max_duration_hours,
    )
    available, min_free = capacity_service.check_availability(place_type, start_at, end_at)
    return AvailabilityResponse(
        place_type=place_type,
        start_at=start_at,
        end_at=end_at,
        available=available,
        min_free_capacity=min_free,
    )
