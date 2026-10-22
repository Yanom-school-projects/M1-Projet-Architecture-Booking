"""Cas d'usage de réservation : création, annulation, traitement des
callbacks de paiement. C'est le cœur métier du service Booking, orchestré
uniquement à travers des ports (UnitOfWork, VehiclesPort, PricingPort,
PaymentPort, EventPublisher) — aucune ligne ici ne connaît SQLAlchemy,
httpx, pika ou FastAPI. Les adaptateurs (adapters/) fournissent les
implémentations concrètes de ces ports, assemblées par
adapters/inbound/http/dependencies.py."""

import random
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.config import Settings
from app.domain.entities import Reservation
from app.domain.enums import PlaceType, ReservationStatus
from app.domain.exceptions import (
    CapacityUnavailableError,
    ExternalServiceError,
    InvalidReservationStateError,
    ReservationIdGenerationError,
    ReservationNotFoundError,
)
from app.domain.rules import validate_slot
from app.ports.event_publisher import EventPublisher
from app.ports.external_services import PaymentPort, PricingPort, VehiclesPort
from app.ports.unit_of_work import UnitOfWork

from .capacity_service import CapacityService

RESERVATION_ID_ATTEMPTS = 20


class ReservationService:
    def __init__(
        self,
        uow: UnitOfWork,
        vehicles: VehiclesPort,
        pricing: PricingPort,
        payment: PaymentPort,
        events: EventPublisher,
        settings: Settings,
    ):
        self._uow = uow
        self._vehicles = vehicles
        self._pricing = pricing
        self._payment = payment
        self._events = events
        self._settings = settings
        self._capacity = CapacityService(uow)

    def _generate_reservation_id(self) -> str:
        """Code à 6 chiffres, pas un UUID : c'est la référence que le client
        communiquera au parking (par oral ou sur un ticket), elle doit
        rester courte. ~1M de combinaisons possibles ; on retire une
        collision avec la base plutôt que de la garantir mathématiquement
        (suffisant vu le volume attendu pour ce MVP)."""
        for _ in range(RESERVATION_ID_ATTEMPTS):
            candidate = f"{random.randint(0, 999_999):06d}"
            if not self._uow.reservations.exists(candidate):
                return candidate
        raise ReservationIdGenerationError("Impossible de générer un identifiant de réservation unique")

    async def create_reservation(
        self,
        vehicle_plate: str,
        email: str,
        place_type: PlaceType,
        start_at: datetime,
        end_at: datetime,
    ) -> Reservation:
        """Vérifie la dispo tôt (retour rapide au client), avant de payer le
        coût d'un appel réseau à Vehicles ; la capacité est re-vérifiée
        juste avant réservation pour couvrir une éventuelle course entre
        deux requêtes concurrentes sur le même créneau."""
        validate_slot(
            start_at,
            end_at,
            now=datetime.utcnow(),
            horizon_days=self._settings.reservation_horizon_days,
            max_duration_hours=self._settings.reservation_max_duration_hours,
        )

        available, _ = self._capacity.check_availability(place_type, start_at, end_at)
        if not available:
            raise CapacityUnavailableError(place_type, start_at)

        vehicle_id = await self._vehicles.resolve_vehicle_id(vehicle_plate)

        self._capacity.reserve(place_type, start_at, end_at)

        reservation = Reservation(
            id=self._generate_reservation_id(),
            vehicle_id=vehicle_id,
            email=email,
            place_type=place_type,
            start_at=start_at,
            end_at=end_at,
            status=ReservationStatus.PENDING_PAYMENT,
        )
        self._uow.reservations.add(reservation)

        try:
            quote = await self._pricing.get_reservation_price(place_type.value, start_at, end_at)
            reservation.price_amount = quote.amount
            reservation.price_reference = quote.reference

            # idempotency_key = id de réservation : un retry de cette requête
            # ne doit jamais déclencher un second encaissement chez Payment.
            attempt = await self._payment.create_payment(
                amount=quote.amount,
                reference=reservation.id,
                idempotency_key=reservation.id,
                callback_url=f"{self._settings.booking_public_url}{self._settings.payment_webhook_path}",
            )
            reservation.payment_id = attempt.payment_id
            self._uow.reservations.update(reservation)
        except Exception as exc:
            # Pricing ou Payment indisponible : on annule proprement plutôt
            # que de laisser une réservation bloquée sans paiement associé.
            self._capacity.release(place_type, start_at, end_at)
            self._uow.reservations.delete(reservation.id)
            self._uow.commit()
            raise ExternalServiceError("Échec de la préparation du paiement, réservation annulée") from exc

        self._uow.commit()
        return reservation

    async def cancel_reservation(self, reservation_id: str) -> Reservation:
        """Annule une réservation confirmée, avec remboursement de la
        moitié du montant payé. La capacité est libérée immédiatement (le
        parking peut revendre le créneau sans attendre le remboursement) ;
        le statut ne passe à `cancelled` qu'une fois le remboursement
        confirmé par Payment, via le même webhook que la confirmation de
        paiement initiale."""
        reservation = self._uow.reservations.get(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        if reservation.status != ReservationStatus.CONFIRMED:
            raise InvalidReservationStateError(
                f"Impossible d'annuler une réservation au statut '{reservation.status.value}'"
            )

        # Le prix à moitié devient le nouveau montant attendu pour cette
        # réservation ; Payment, en le comparant à ce qu'il a déjà encaissé
        # pour la même référence, rembourse la différence.
        new_amount = (reservation.price_amount / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        refund_amount = reservation.price_amount - new_amount

        self._capacity.release(reservation.place_type, reservation.start_at, reservation.end_at)
        reservation.status = ReservationStatus.CANCELLATION_PENDING
        reservation.refund_amount = refund_amount
        self._uow.reservations.update(reservation)

        try:
            # Même reference (l'id de réservation) que le paiement initial,
            # mais un idempotency_key distinct : c'est une opération à part,
            # pas un retry de la précédente.
            await self._payment.create_payment(
                amount=new_amount,
                reference=reservation.id,
                idempotency_key=f"{reservation.id}:cancel",
                callback_url=f"{self._settings.booking_public_url}{self._settings.payment_webhook_path}",
            )
        except Exception as exc:
            self._uow.rollback()
            raise ExternalServiceError("Échec de la demande de remboursement auprès de Payment") from exc

        self._uow.commit()
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation:
        reservation = self._uow.reservations.get(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        return reservation

    def list_reservations(self, vehicle_id: Optional[str]) -> list[Reservation]:
        """Utilisé notamment par le service Access pour vérifier qu'un
        véhicule qui se présente à l'entrée possède une réservation
        valable. Sans `vehicle_id`, renvoie toutes les réservations."""
        return self._uow.reservations.list_by_vehicle(vehicle_id)

    def handle_payment_webhook(self, payment_id: str, status: str, reference: str) -> Optional[Reservation]:
        """Traite le callback asynchrone de Payment, qu'il s'agisse de la
        confirmation d'un paiement initial ou d'un remboursement suite à
        annulation. La corrélation se fait uniquement sur `reference` (l'id
        de réservation) : pour un remboursement, Payment peut légitimement
        attribuer un nouveau `payment_id` à l'opération, `reference` reste
        la seule constante sur tout le cycle de vie."""
        reservation = self._uow.reservations.get(reference)
        if reservation is None:
            return None

        if reservation.status == ReservationStatus.PENDING_PAYMENT:
            if status == "paid":
                reservation.status = ReservationStatus.CONFIRMED
                self._uow.reservations.update(reservation)
                self._uow.commit()
                self._events.publish(
                    "reservation.confirmed",
                    {
                        "reservation_id": reservation.id,
                        "vehicle_id": reservation.vehicle_id,
                        "email": reservation.email,
                        # Pas de numéro de place nominal ici : le cadrage
                        # métier gère la capacité par comptage, pas par place
                        # numérotée (l'attribution physique se fait à
                        # l'entrée, côté Access/Parking).
                        "place_type": reservation.place_type.value,
                        "start_at": reservation.start_at.isoformat(),
                        "end_at": reservation.end_at.isoformat(),
                        "price_amount": str(reservation.price_amount),
                        "payment_id": reservation.payment_id,
                    },
                )
            elif status in ("refused", "cancelled"):
                reservation.status = ReservationStatus.FAILED
                self._capacity.release(reservation.place_type, reservation.start_at, reservation.end_at)
                self._uow.reservations.update(reservation)
                self._uow.commit()
            # "pending" : rien à faire, on attend le prochain callback

        elif reservation.status == ReservationStatus.CANCELLATION_PENDING:
            if status == "refunded":
                reservation.status = ReservationStatus.CANCELLED
                self._uow.reservations.update(reservation)
                self._uow.commit()
                self._events.publish(
                    "reservation.cancelled",
                    {
                        "reservation_id": reservation.id,
                        "vehicle_id": reservation.vehicle_id,
                        "email": reservation.email,
                        "refund_amount": str(reservation.refund_amount),
                    },
                )
            # tout autre statut intermédiaire : on attend encore la confirmation du remboursement

        # tout autre statut de réservation (confirmed, cancelled, failed) est
        # terminal : callback idempotent, un rejeu n'a plus d'effet.

        return reservation
