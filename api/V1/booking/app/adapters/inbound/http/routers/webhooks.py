from fastapi import APIRouter, Depends

from app.application.reservation_service import ReservationService

from ..dependencies import get_reservation_service
from ..schemas import PaymentWebhookPayload

router = APIRouter()


@router.post(
    "/webhooks/payment",
    summary="Callback de statut de paiement (appelé par Payment)",
    response_description="Accusé de réception du callback.",
)
def payment_webhook(
    payload: PaymentWebhookPayload,
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Point d'entrée asynchrone appelé par le service **Payment** quand le
    statut d'un paiement évolue (typiquement `pending` → `paid`).

    - `paid` confirme la réservation et publie l'événement `reservation.confirmed` ;
    - `refused`/`cancelled` fait échouer la réservation et libère la capacité réservée ;
    - `refunded` (annulation) confirme le remboursement et publie `reservation.cancelled` ;
    - `pending` ou tout autre statut intermédiaire n'a aucun effet, en
      attendant un prochain callback avec le statut final.

    Traitement idempotent : si la réservation n'est déjà plus dans l'état
    attendu, le callback est ignoré silencieusement (rejeu réseau, etc.).
    """
    reservation_service.handle_payment_webhook(payload.payment_id, payload.status, payload.reference)
    return {"received": True}
