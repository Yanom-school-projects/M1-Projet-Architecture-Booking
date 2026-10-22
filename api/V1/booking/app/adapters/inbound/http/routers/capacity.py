from fastapi import APIRouter, Depends

from app.application.capacity_service import CapacityService

from ..dependencies import get_capacity_service
from ..schemas import CapacityAllocationRequest

router = APIRouter()


@router.put(
    "/capacity",
    summary="Allouer la capacité réservable d'un créneau",
    response_description="L'état de la capacité après application de l'allocation.",
)
def set_capacity(
    payload: CapacityAllocationRequest,
    capacity_service: CapacityService = Depends(get_capacity_service),
):
    """Appelé par le service **Parking** pour indiquer combien de places d'un
    type donné sont mises à disposition de Booking sur un créneau horaire.

    Remplace la valeur allouée précédente pour ce créneau (opération
    idempotente) ; n'affecte pas les places déjà réservées (`booked`).
    """
    slot = capacity_service.set_allocation(payload.place_type, payload.slot_start, payload.allocated)
    capacity_service.commit()
    return {"place_type": slot.place_type, "slot_start": slot.slot_start, "allocated": slot.allocated}
