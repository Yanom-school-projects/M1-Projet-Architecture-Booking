from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query

from app.application.reservation_service import ReservationService

from ..dependencies import get_reservation_service, poll_payment_until_final
from ..schemas import ReservationCheckResponse, ReservationCreateRequest, ReservationResponse, to_utc_naive

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
    background_tasks: BackgroundTasks,
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Orchestre la création d'une réservation :

    1. valide le créneau (heures pleines, horizon 30 jours, durée max 7 jours) ;
    2. vérifie et réserve la capacité disponible ;
    3. résout la plaque en identifiant pseudonymisé auprès de Vehicles ;
    4. demande le prix à Pricing ;
    5. déclenche le paiement auprès de Payment.

    La réservation est renvoyée avec le statut `pending_payment` : Payment
    met en général 15 à 30 s à trancher. Booking interroge Payment en tâche
    de fond et passe la réservation à `confirmed` ou `failed`. Le client
    suit l'issue avec `GET /reservations/{id}`.
    """
    reservation = await reservation_service.create_reservation(
        vehicle_plate=payload.vehicle_plate,
        email=payload.email,
        place_type=payload.place_type,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )
    background_tasks.add_task(poll_payment_until_final, reservation.id)
    return reservation


@router.post(
    "/reservations/{reservation_id}/cancel",
    summary="Annuler une réservation confirmée (sans remboursement)",
    response_model=ReservationResponse,
    responses={
        404: {"description": "Aucune réservation avec cet identifiant."},
        409: {"description": "La réservation n'est pas confirmée (déjà annulée, en attente de paiement, etc.)."},
    },
)
def cancel_reservation(
    reservation_id: str = Path(..., pattern=r"^\d{6}$", description="Code de réservation à 6 chiffres."),
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Annule une réservation **confirmée** et libère immédiatement la place
    pour d'autres réservations. **Aucun remboursement** : le service Payment
    ne gère pas les remboursements. Publie l'événement `reservation.cancelled`.
    """
    return reservation_service.cancel_reservation(reservation_id)


# Déclarée avant /reservations/{reservation_id} : sinon « active » serait lu
# comme un code de réservation.
@router.get(
    "/reservations/active",
    summary="Vérifier qu'un véhicule a une réservation valable maintenant (Access)",
    response_model=ReservationCheckResponse,
)
async def check_active_reservation(
    vehicle_id: str = Query(..., min_length=1, description="Identifiant pseudonymisé fourni par Vehicles."),
    at: Optional[datetime] = Query(
        None,
        description="Instant à vérifier. Par défaut : maintenant. Sans fuseau, la date est lue comme de l'UTC.",
    ),
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Appelé par **Access** quand un véhicule se présente à l'entrée.

    Une réservation est valable si elle est `confirmed` (paiement accepté) et
    que l'instant vérifié est dans son créneau : `start_at <= at < end_at`.
    Pas de tolérance d'avance ou de retard (hors périmètre).

    Répond toujours 200 : `valid` dit si l'entrée peut se faire au titre
    d'une réservation, et `reservations` donne le type de place réservé.
    """
    at = to_utc_naive(at) if at is not None else datetime.utcnow()
    reservations = await reservation_service.find_valid_reservations(vehicle_id, at)
    return ReservationCheckResponse(
        vehicle_id=vehicle_id,
        at=at,
        valid=bool(reservations),
        reservations=reservations,
    )


@router.get(
    "/reservations/{reservation_id}",
    summary="Consulter une réservation par son identifiant",
    response_model=ReservationResponse,
    responses={404: {"description": "Aucune réservation avec cet identifiant."}},
)
async def get_reservation(
    reservation_id: str = Path(..., pattern=r"^\d{6}$", description="Code de réservation à 6 chiffres."),
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Renvoie l'état courant d'une réservation, notamment utile pour
    suivre la transition `pending_payment` → `confirmed`/`failed`. Si le
    paiement est encore en attente, son statut est redemandé à Payment."""
    return await reservation_service.get_reservation(reservation_id)


@router.get(
    "/reservations",
    summary="Lister les réservations d'un véhicule",
    response_model=list[ReservationResponse],
)
def list_reservations(
    vehicle_id: Optional[str] = None,
    reservation_service: ReservationService = Depends(get_reservation_service),
):
    """Historique complet des réservations d'un véhicule, tous statuts
    confondus. Pour décider d'une entrée, Access utilise plutôt
    `GET /reservations/active`. Sans `vehicle_id`, renvoie toutes les
    réservations (usage interne/debug)."""
    return reservation_service.list_reservations(vehicle_id)
