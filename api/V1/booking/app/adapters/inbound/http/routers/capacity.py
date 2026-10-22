from fastapi import APIRouter, Depends

from app.application.capacity_service import CapacityService

from ..dependencies import get_capacity_service
from ..schemas import CapacityAllocationRequest

router = APIRouter()


@router.put(
    "/capacity",
    summary="Allouer la capacité réservable d'un créneau",
    response_description="L'état de la capacité après application de l'allocation.",
    responses={
        409: {"description": "Allocation inférieure au nombre de places déjà réservées sur ce créneau."},
        422: {"description": "slot_start n'est pas une heure pleine, ou allocated est négatif."},
    },
)
def set_capacity(
    payload: CapacityAllocationRequest,
    capacity_service: CapacityService = Depends(get_capacity_service),
):
    """Appelé par le service **Parking** pour indiquer combien de places d'un
    type donné sont mises à disposition de Booking sur un créneau horaire.

    Remplace la valeur allouée précédente pour ce créneau (opération
    idempotente) ; n'affecte pas les places déjà réservées (`booked`) et
    refuse de descendre en dessous de ce nombre.
    """
    slot = capacity_service.set_allocation(payload.place_type, payload.slot_start, payload.allocated)
    capacity_service.commit()
    return {"place_type": slot.place_type, "slot_start": slot.slot_start, "allocated": slot.allocated}
