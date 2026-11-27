from datetime import datetime

from fastapi import APIRouter, Depends, Path

from app.adapters.outbound.metrics.prometheus_metrics import business_metrics
from app.application.capacity_service import CapacityService
from app.domain.enums import PlaceType
from app.ports.metrics import Operation, Result

from ..dependencies import get_capacity_service
from ..schemas import CapacityAllocationRequest, CapacitySlotResponse, to_utc_naive

router = APIRouter()


@router.put(
    "/capacity-slots/{place_type}/{slot_start}",
    summary="Fixer le nombre de places réservables d'un créneau horaire",
    response_model=CapacitySlotResponse,
    response_description="L'état du créneau après application de l'allocation.",
    responses={
        409: {"description": "Allocation inférieure au nombre de places déjà réservées sur ce créneau."},
        422: {"description": "slot_start ne tombe pas sur un quart d'heure, ou allocated est négatif."},
    },
)
def set_capacity_slot(
    payload: CapacityAllocationRequest,
    place_type: PlaceType = Path(..., description="Type de place concerné."),
    slot_start: datetime = Path(
        ...,
        description="Début du quart d'heure, ex. `2026-11-26T09:15:00`. Sans fuseau, la date est lue comme de l'UTC.",
    ),
    capacity_service: CapacityService = Depends(get_capacity_service),
):
    """Indique combien de places d'un type donné sont mises à disposition de
    Booking sur un quart d'heure. En temps normal, cette valeur vient
    de la synchronisation avec **Parking** (`POST /capacity-slots/sync`) ;
    cette route sert à ajuster un créneau précis (tests, correction manuelle).

    Remplace la valeur précédente du créneau (opération idempotente) ; ne
    touche pas aux places déjà réservées (`booked`) et refuse de descendre
    en dessous de ce nombre.
    """
    try:
        slot = capacity_service.set_allocation(place_type, to_utc_naive(slot_start), payload.allocated)
        capacity_service.commit()
    except Exception:
        business_metrics.record(Operation.CAPACITY_UPDATE, Result.ERROR)
        raise
    business_metrics.record(Operation.CAPACITY_UPDATE, Result.SUCCESS)
    return slot
