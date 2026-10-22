from datetime import datetime

from fastapi import APIRouter, Depends

from app.application.capacity_service import CapacityService
from app.domain.enums import PlaceType

from ..dependencies import get_capacity_service
from ..schemas import AvailabilityResponse

router = APIRouter()


@router.get(
    "/availability",
    summary="Consulter la capacité disponible sur un créneau",
    response_model=AvailabilityResponse,
    response_description="Disponibilité et capacité minimale libre sur le créneau demandé.",
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
    """
    available, min_free = capacity_service.check_availability(place_type, start_at, end_at)
    capacity_service.commit()  # persiste les créneaux 0/0 créés en lecture (voir get_or_create)
    return AvailabilityResponse(
        place_type=place_type,
        start_at=start_at,
        end_at=end_at,
        available=available,
        min_free_capacity=min_free,
    )
