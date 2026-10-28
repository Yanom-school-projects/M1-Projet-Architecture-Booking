"""Cas d'usage de réservation : création, annulation, suivi du statut de
paiement. C'est le cœur métier du service Booking, orchestré
uniquement à travers des ports (UnitOfWork, VehiclesPort, PricingPort,
PaymentPort, EventPublisher) — aucune ligne ici ne connaît SQLAlchemy,
httpx, pika ou FastAPI. Les adaptateurs (adapters/) fournissent les
implémentations concrètes de ces ports, assemblées par
adapters/inbound/http/dependencies.py."""

import asyncio
import logging
import random
import uuid
from datetime import datetime
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
from app.domain.value_objects import PaymentStatus
from app.ports.event_publisher import EventPublisher
from app.ports.external_services import PaymentPort, PricingPort, VehiclesPort
from app.ports.unit_of_work import UnitOfWork

from .capacity_service import CapacityService

RESERVATION_ID_ATTEMPTS = 20

logger = logging.getLogger("booking.reservations")


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

        # Réveille Pricing et Payment en même temps, pendant l'appel à
        # Vehicles : sur Render gratuit, leurs démarrages se chevauchent au
        # lieu de s'additionner.
        wake_up = asyncio.gather(self._pricing.wake_up(), self._payment.wake_up())
        try:
            vehicle_id = await self._vehicles.resolve_vehicle_id(vehicle_plate)
        except Exception:
            wake_up.cancel()
            raise
        await wake_up

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

            # Clé d'idempotence générée une fois pour cette opération : un
            # retry réseau doit réutiliser la même. Le suffixe aléatoire évite
            # qu'un code à 6 chiffres réutilisé plus tard (base réinitialisée,
            # réservation supprimée) retombe sur un ancien paiement.
            attempt = await self._payment.create_payment(
                amount=quote.amount,
                reference=reservation.id,
                idempotency_key=f"booking-{reservation.id}-{uuid.uuid4().hex[:8]}",
            )
            reservation.payment_id = attempt.payment_id
            self._uow.reservations.update(reservation)
        except Exception as exc:
            # Pricing ou Payment indisponible : on annule proprement plutôt
            # que de laisser une réservation bloquée sans paiement associé.
            logger.error("Échec Pricing/Payment pour la réservation %s : %r", reservation.id, exc)
            self._capacity.release(place_type, start_at, end_at)
            self._uow.reservations.delete(reservation.id)
            self._uow.commit()
            raise ExternalServiceError("Échec de la préparation du paiement, réservation annulée") from exc

        self._uow.commit()
        return reservation

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        """Annule une réservation confirmée et libère la capacité, sans
        remboursement : le service Payment ne gère pas les remboursements.
        Extension par rapport aux règles métier (§2.7, réservation « non
        annulable »), à présenter comme telle."""
        reservation = self._uow.reservations.get(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        if reservation.status != ReservationStatus.CONFIRMED:
            raise InvalidReservationStateError(
                f"Impossible d'annuler une réservation au statut '{reservation.status.value}'"
            )

        if not self._uow.reservations.transition_status(
            reservation.id, ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED
        ):
            self._uow.rollback()
            raise InvalidReservationStateError("La réservation vient de changer de statut, annulation impossible")
        self._capacity.release(reservation.place_type, reservation.start_at, reservation.end_at)
        self._uow.commit()
        reservation.status = ReservationStatus.CANCELLED
        self._events.publish(
            "reservation.cancelled",
            {
                "reservation_id": reservation.id,
                "vehicle_id": reservation.vehicle_id,
                "email": reservation.email,
                "place_type": reservation.place_type.value,
                "start_at": reservation.start_at.isoformat(),
                "end_at": reservation.end_at.isoformat(),
            },
        )
        return reservation

    async def get_reservation(self, reservation_id: str) -> Reservation:
        """Si le paiement est encore en attente, demande son statut à Payment
        avant de répondre : le client voit l'état à jour même si le suivi en
        tâche de fond a été interrompu (redémarrage du service)."""
        reservation = self._uow.reservations.get(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        return await self.sync_payment_status(reservation)

    def list_reservations(self, vehicle_id: Optional[str]) -> list[Reservation]:
        """Historique des réservations d'un véhicule, tous statuts confondus.
        Sans `vehicle_id`, renvoie toutes les réservations."""
        return self._uow.reservations.list_by_vehicle(vehicle_id)

    async def find_valid_reservations(self, vehicle_id: str, at: datetime) -> list[Reservation]:
        """Réservations qui autorisent le véhicule à entrer à l'instant `at` :
        statut `confirmed` et `start_at <= at < end_at`. Pas de tolérance
        d'avance ou de retard (hors périmètre du cadrage métier).

        Une réservation encore `pending_payment` sur ce créneau est d'abord
        mise à jour auprès de Payment : si le suivi en tâche de fond a été
        interrompu (redémarrage), le client n'est pas bloqué à la barrière
        alors que son paiement est accepté."""
        candidates = self._uow.reservations.list_covering(
            vehicle_id, at, [ReservationStatus.CONFIRMED, ReservationStatus.PENDING_PAYMENT]
        )
        valid = []
        for reservation in candidates:
            reservation = await self.sync_payment_status(reservation)
            if reservation.status == ReservationStatus.CONFIRMED:
                valid.append(reservation)
        return valid

    async def sync_payment_status(self, reservation: Reservation) -> Reservation:
        """Interroge Payment pour une réservation en attente de paiement et
        applique le statut final :
        - ACCEPTED : réservation confirmée, événement `reservation.confirmed` ;
        - REFUSED : réservation en échec, capacité libérée ;
        - PENDING : rien à faire, on redemandera plus tard.

        Idempotent : une réservation qui n'est plus en attente n'est pas
        modifiée. Une panne de Payment est loguée sans faire échouer
        l'appelant : la réservation reste simplement en attente."""
        if reservation.status != ReservationStatus.PENDING_PAYMENT or not reservation.payment_id:
            return reservation

        try:
            attempt = await self._payment.get_payment(reservation.payment_id)
        except Exception:
            logger.warning("Statut du paiement %s indisponible", reservation.payment_id, exc_info=True)
            return reservation

        if attempt.status == PaymentStatus.ACCEPTED:
            changed = self._uow.reservations.transition_status(
                reservation.id, ReservationStatus.PENDING_PAYMENT, ReservationStatus.CONFIRMED
            )
            self._uow.commit()
            if not changed:
                # Déjà traité par un appel concurrent : pas de second événement.
                return self._uow.reservations.get(reservation.id)
            reservation.status = ReservationStatus.CONFIRMED
            logger.info("Réservation %s confirmée (paiement %s)", reservation.id, reservation.payment_id)
            self._events.publish(
                "reservation.confirmed",
                {
                    "reservation_id": reservation.id,
                    "vehicle_id": reservation.vehicle_id,
                    "email": reservation.email,
                    # Pas de numéro de place : la capacité est gérée par
                    # comptage, l'attribution physique se fait à l'entrée.
                    "place_type": reservation.place_type.value,
                    "start_at": reservation.start_at.isoformat(),
                    "end_at": reservation.end_at.isoformat(),
                    "price_amount": str(reservation.price_amount),
                    "payment_id": reservation.payment_id,
                },
            )
        elif attempt.status == PaymentStatus.REFUSED:
            changed = self._uow.reservations.transition_status(
                reservation.id, ReservationStatus.PENDING_PAYMENT, ReservationStatus.FAILED
            )
            if not changed:
                # Déjà traité par un appel concurrent : ne pas libérer la place deux fois.
                self._uow.commit()
                return self._uow.reservations.get(reservation.id)
            self._capacity.release(reservation.place_type, reservation.start_at, reservation.end_at)
            self._uow.commit()
            reservation.status = ReservationStatus.FAILED
            logger.info("Réservation %s en échec (paiement %s refusé)", reservation.id, reservation.payment_id)

        return reservation
