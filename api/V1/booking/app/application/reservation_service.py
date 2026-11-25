"""Cas d'usage de réservation : création, annulation, suivi du statut de
paiement. C'est le cœur métier du service Booking, orchestré
uniquement à travers des ports (UnitOfWork, VehiclesPort, PricingPort,
PaymentPort, EventPublisher, BusinessMetrics) — aucune ligne ici ne connaît SQLAlchemy,
httpx, pika ou FastAPI. Les adaptateurs (adapters/) fournissent les
implémentations concrètes de ces ports, assemblées par
adapters/inbound/http/dependencies.py."""

import asyncio
import logging
import random
from datetime import datetime
from enum import Enum
from typing import Optional

from app.config import Settings
from app.correlation import correlation_scope, get_correlation_id
from app.domain.entities import Reservation
from app.domain.enums import PlaceType, ReservationStatus
from app.domain.exceptions import (
    CapacityUnavailableError,
    ExternalServiceError,
    InvalidReservationStateError,
    PaymentOutcomeUnknownError,
    PaymentRejectedError,
    ReservationIdGenerationError,
    ReservationNotFoundError,
)
from app.domain.rules import validate_slot
from app.domain.value_objects import PaymentStatus
from app.ports.event_publisher import EventPublisher
from app.ports.external_services import PaymentPort, PricingPort, VehiclesPort
from app.ports.metrics import BusinessMetrics, NoOpBusinessMetrics, Operation, Result
from app.ports.unit_of_work import UnitOfWork

from .capacity_service import CapacityService

RESERVATION_ID_ATTEMPTS = 20


class PaymentRequestOutcome(Enum):
    CREATED = "created"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


def payment_idempotency_key(reservation_id: str) -> str:
    """Clé d'idempotence de la demande de paiement, au format convenu avec
    Payment : elle identifie l'opération métier (payer cette réservation),
    pas l'appel HTTP. Identique à chaque nouvel essai ; unique par
    réservation car un code de réservation n'est jamais réattribué."""
    return f"booking:{reservation_id}:create"

logger = logging.getLogger("booking.reservations")


def _log_switch_to_reservation(reservation: Reservation, action: str) -> None:
    """Quand une requête agit sur une réservation créée par une autre, les
    logs qui suivent passent sur l'identifiant de la réservation : cette ligne,
    écrite avec l'identifiant de la requête, fait le lien entre les deux."""
    current = get_correlation_id()
    if reservation.correlation_id and current and current != reservation.correlation_id:
        logger.info("%s de la réservation %s (parcours %s)", action, reservation.id, reservation.correlation_id)


class ReservationService:
    def __init__(
        self,
        uow: UnitOfWork,
        vehicles: VehiclesPort,
        pricing: PricingPort,
        payment: PaymentPort,
        events: EventPublisher,
        settings: Settings,
        metrics: Optional[BusinessMetrics] = None,
    ):
        self._uow = uow
        self._vehicles = vehicles
        self._pricing = pricing
        self._payment = payment
        self._events = events
        self._settings = settings
        self._metrics = metrics or NoOpBusinessMetrics()
        self._capacity = CapacityService(uow)

    def _publish_event(self, event_type: str, reservation_id: str, payload: dict) -> None:
        """Publie un événement sans faire échouer l'appelant : le changement de
        statut est déjà validé en base, une panne du bus ne doit ni renvoyer
        une 500 au client ni interrompre le suivi du paiement. L'événement
        perdu est logué en ERROR pour pouvoir le renvoyer à la main.
        TODO : outbox (événements stockés en base, renvoyés en tâche de fond)
        pour ne plus dépendre d'une intervention manuelle."""
        try:
            self._events.publish(event_type, payload)
        except Exception:
            logger.exception("Événement %s NON publié pour la réservation %s", event_type, reservation_id)

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
        """Compte chaque demande : success si la réservation est créée (en
        attente de paiement), error pour tout refus (créneau invalide, plus de
        place, service dépendant en panne)."""
        try:
            reservation = await self._create_reservation(vehicle_plate, email, place_type, start_at, end_at)
        except Exception:
            self._metrics.record(Operation.RESERVATION_CREATE, Result.ERROR)
            raise
        self._metrics.record(Operation.RESERVATION_CREATE, Result.SUCCESS)
        return reservation

    async def _create_reservation(
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
            correlation_id=get_correlation_id(),
        )
        reservation.payment_idempotency_key = payment_idempotency_key(reservation.id)
        self._uow.reservations.add(reservation)

        try:
            quote = await self._pricing.get_reservation_price(place_type.value, start_at, end_at)
        except Exception as exc:
            # Aucun paiement n'a encore été demandé : échec certain.
            logger.error("Échec Pricing pour la réservation %s : %r", reservation.id, exc)
            self._mark_failed(reservation, "tarification impossible")
            raise ExternalServiceError("Échec de la tarification, réservation annulée") from exc

        reservation.price_amount = quote.amount
        reservation.price_reference = quote.reference
        self._uow.reservations.update(reservation)
        # Validé AVANT d'appeler Payment : si Booking s'arrête pendant l'appel,
        # la réservation et sa clé existent toujours, et la demande pourra
        # être renvoyée avec la même clé au lieu de laisser un paiement orphelin.
        self._uow.commit()
        logger.info(
            "Réservation %s créée : %s du %s au %s, %s EUR, clé de paiement %s",
            reservation.id,
            place_type.value,
            start_at.isoformat(),
            end_at.isoformat(),
            reservation.price_amount,
            reservation.payment_idempotency_key,
        )

        if await self._request_payment(reservation) == PaymentRequestOutcome.REJECTED:
            raise ExternalServiceError("Demande de paiement refusée par Payment, réservation annulée")
        return reservation

    async def _request_payment(self, reservation: Reservation) -> PaymentRequestOutcome:
        """Demande le paiement à Payment avec la clé d'idempotence de la
        réservation. Sans risque de double débit : chaque nouvel essai (ici,
        dans le suivi en tâche de fond ou à la prochaine consultation) envoie
        la même clé, et Payment renvoie le paiement existant s'il l'a créé.

        - accepté par Payment : payment_id enregistré ;
        - refusé (422) : réservation en échec, place libérée ;
        - issue inconnue (timeout, réseau, 5xx, 401, 409) : la réservation reste en
          attente, la demande sera renvoyée plus tard avec la même clé."""
        try:
            attempt = await self._payment.create_payment(
                amount=reservation.price_amount,
                reference=reservation.id,
                idempotency_key=reservation.payment_idempotency_key,
            )
        except PaymentRejectedError:
            if self._mark_failed(reservation, "demande de paiement refusée par Payment"):
                self._metrics.record(Operation.RESERVATION_PAYMENT, Result.REFUSED)
            return PaymentRequestOutcome.REJECTED
        except PaymentOutcomeUnknownError:
            logger.warning(
                "Réservation %s : issue de la demande de paiement inconnue, nouvel essai plus tard avec la clé %s",
                reservation.id,
                reservation.payment_idempotency_key,
            )
            return PaymentRequestOutcome.UNKNOWN

        reservation.payment_id = attempt.payment_id
        self._uow.reservations.set_payment_id(reservation.id, attempt.payment_id)
        self._uow.commit()
        logger.info("Réservation %s : paiement %s demandé", reservation.id, attempt.payment_id)
        return PaymentRequestOutcome.CREATED

    def _mark_failed(self, reservation: Reservation, reason: str) -> bool:
        """pending_payment -> failed et libère la place. La réservation n'est
        jamais supprimée : son code reste pris et ne sera pas réattribué, ce
        qui garantit qu'une clé booking:{id}:create désigne un seul paiement."""
        changed = self._uow.reservations.transition_status(
            reservation.id, ReservationStatus.PENDING_PAYMENT, ReservationStatus.FAILED
        )
        if changed:
            self._capacity.release(reservation.place_type, reservation.start_at, reservation.end_at)
        self._uow.commit()
        if changed:
            reservation.status = ReservationStatus.FAILED
            logger.info("Réservation %s en échec (%s), capacité libérée", reservation.id, reason)
        return changed

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        """Annule une réservation confirmée et libère la capacité, sans
        remboursement : le service Payment ne gère pas les remboursements.
        Extension par rapport aux règles métier (§2.7, réservation « non
        annulable »), à présenter comme telle."""
        reservation = self._uow.reservations.get(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        _log_switch_to_reservation(reservation, "Annulation")
        with correlation_scope(reservation.correlation_id):
            try:
                cancelled = self._cancel(reservation)
            except Exception:
                self._metrics.record(Operation.RESERVATION_CANCEL, Result.ERROR)
                raise
        self._metrics.record(Operation.RESERVATION_CANCEL, Result.SUCCESS)
        return cancelled

    def _cancel(self, reservation: Reservation) -> Reservation:
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
        logger.info("Réservation %s annulée par le client, capacité libérée", reservation.id)
        self._publish_event(
            "reservation.cancelled",
            reservation.id,
            {
                "reservation_id": reservation.id,
                "vehicle_id": reservation.vehicle_id,
                "email": reservation.email,
                "place_type": reservation.place_type.value,
                "place_type_label": reservation.place_type.label,
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
        self._metrics.record(Operation.ACCESS_CHECK, Result.VALID if valid else Result.INVALID)
        return valid

    async def sync_payment_status(self, reservation: Reservation) -> Reservation:
        """Interroge Payment pour une réservation en attente de paiement et
        applique le statut final :
        - ACCEPTED : réservation confirmée, événement `reservation.confirmed` ;
        - REFUSED : réservation en échec, capacité libérée ;
        - PENDING : rien à faire, on redemandera plus tard.

        Idempotent : une réservation qui n'est plus en attente n'est pas
        modifiée. Une panne de Payment est loguée sans faire échouer
        l'appelant : la réservation reste simplement en attente.

        L'appel à Payment, les logs et l'événement portent l'identifiant de
        corrélation de la réservation, même si l'appel vient d'une autre
        requête (consultation par le client, vérification par Access).

        Si la demande de paiement n'a pas encore abouti (issue inconnue lors
        de la création), elle est d'abord renvoyée avec la même clé."""
        if reservation.status != ReservationStatus.PENDING_PAYMENT:
            return reservation
        _log_switch_to_reservation(reservation, "Vérification du paiement")
        with correlation_scope(reservation.correlation_id):
            return await self._apply_payment_status(reservation)

    async def _apply_payment_status(self, reservation: Reservation) -> Reservation:
        if not reservation.payment_id:
            if not reservation.payment_idempotency_key or reservation.price_amount is None:
                # Créée avant les clés stockées : rien à renvoyer.
                return reservation
            if await self._request_payment(reservation) != PaymentRequestOutcome.CREATED:
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
            self._metrics.record(Operation.RESERVATION_PAYMENT, Result.ACCEPTED)
            logger.info("Réservation %s confirmée (paiement %s)", reservation.id, reservation.payment_id)
            self._publish_event(
                "reservation.confirmed",
                reservation.id,
                {
                    "reservation_id": reservation.id,
                    "vehicle_id": reservation.vehicle_id,
                    "email": reservation.email,
                    # Pas de numéro de place : la capacité est gérée par
                    # comptage, l'attribution physique se fait à l'entrée.
                    "place_type": reservation.place_type.value,
                    "place_type_label": reservation.place_type.label,
                    "start_at": reservation.start_at.isoformat(),
                    "end_at": reservation.end_at.isoformat(),
                    "price_amount": str(reservation.price_amount),
                    "payment_id": reservation.payment_id,
                },
            )
        elif attempt.status == PaymentStatus.REFUSED:
            if not self._mark_failed(reservation, f"paiement {reservation.payment_id} refusé"):
                # Déjà traité par un appel concurrent : la place n'est pas libérée deux fois.
                return self._uow.reservations.get(reservation.id)
            self._metrics.record(Operation.RESERVATION_PAYMENT, Result.REFUSED)

        return reservation
