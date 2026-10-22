from typing import Optional

from fastapi import APIRouter, Depends, Path

from app.application.reservation_service import ReservationService

from ..dependencies import get_reservation_service
from ..schemas import ReservationCreateRequest, ReservationResponse

router = APIRouter()


@router.post(
    "/reservations",
    summary="Créer une réservation",
    response_model=ReservationResponse,
    status_code=201,
    responses={
        409: {"description": "Aucune capacité disponible sur ce créneau."},
        422: {"description": "Créneau invalide (non aligné sur une heure pleine, passé, ou trop long/lointain)."},
        502: {"description": "Un service dépendant (Vehicles, Pricing ou Payment) n'a pas répondu correctement."},
    },
)
async def create_reservation(
    payload: ReservationCreateRequest,
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Orchestre la création d'une réservation :

    1. valide le créneau (heures pleines, horizon 30 jours, durée max 7 jours) ;
    2. vérifie et réserve la capacité disponible ;
    3. résout la plaque en identifiant pseudonymisé auprès de Vehicles ;
    4. demande le prix à Pricing ;
    5. déclenche le paiement auprès de Payment.

    La réservation est renvoyée avec le statut `pending_payment` : le
    paiement peut mettre quelques instants à être confirmé. Le client doit
    ensuite interroger `GET /reservations/{id}` (ou attendre l'événement
    `reservation.confirmed`) pour connaître l'issue finale.
    """
    return await reservation_service.create_reservation(
        vehicle_plate=payload.vehicle_plate,
        email=payload.email,
        place_type=payload.place_type,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )


@router.post(
    "/reservations/{reservation_id}/cancel",
    summary="Annuler une réservation confirmée (remboursement de 50%)",
    response_model=ReservationResponse,
    responses={
        404: {"description": "Aucune réservation avec cet identifiant."},
        409: {"description": "La réservation n'est pas dans un état annulable (déjà annulée, en attente de paiement, etc.)."},
        502: {"description": "Payment n'a pas répondu correctement à la demande de remboursement."},
    },
)
async def cancel_reservation(
    reservation_id: str = Path(..., pattern=r"^\d{6}$", description="Code de réservation à 6 chiffres."),
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Annule une réservation **confirmée** : le client est remboursé de la
    moitié du montant payé, l'autre moitié reste acquise au parking. La
    place redevient immédiatement disponible pour d'autres réservations.

    Statut renvoyé : `cancellation_pending` (remboursement en cours). Le
    statut final `cancelled` n'est atteint qu'après confirmation du
    remboursement par Payment — interroger `GET /reservations/{id}` pour le
    suivre, comme pour la confirmation de paiement initiale.
    """
    return await reservation_service.cancel_reservation(reservation_id)


@router.get(
    "/reservations/{reservation_id}",
    summary="Consulter une réservation par son identifiant",
    response_model=ReservationResponse,
    responses={404: {"description": "Aucune réservation avec cet identifiant."}},
)
def get_reservation(
    reservation_id: str = Path(..., pattern=r"^\d{6}$", description="Code de réservation à 6 chiffres."),
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Renvoie l'état courant d'une réservation, notamment utile pour
    suivre la transition `pending_payment` → `confirmed`/`failed`."""
    return reservation_service.get_reservation(reservation_id)


@router.get(
    "/reservations",
    summary="Lister les réservations d'un véhicule",
    response_model=list[ReservationResponse],
)
def list_reservations(
    vehicle_id: Optional[str] = None,
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Utilisé notamment par le service Access pour vérifier qu'un véhicule
    qui se présente à l'entrée possède une réservation valable. Sans
    `vehicle_id`, renvoie toutes les réservations (usage interne/debug)."""
    return reservation_service.list_reservations(vehicle_id)
