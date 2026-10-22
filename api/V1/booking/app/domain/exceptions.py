"""Exceptions métier. Le domaine et la couche application ne connaissent
aucun code HTTP : c'est l'adaptateur entrant (adapters/inbound/http) qui
traduit chaque type d'exception en code de statut, de façon centralisée
(voir exception_handlers.py) plutôt qu'éparpillée dans chaque route."""

from datetime import datetime

from .enums import PlaceType


class DomainError(Exception):
    """Base commune à toutes les erreurs métier de Booking."""


class InvalidSlotError(DomainError):
    """Créneau invalide : alignement sur une heure pleine, horizon de
    réservation ou durée maximum."""


class CapacityUnavailableError(DomainError):
    def __init__(self, place_type: PlaceType, slot_start: datetime):
        self.place_type = place_type
        self.slot_start = slot_start
        super().__init__("Aucune capacité disponible sur ce créneau")


class CapacityBelowBookedError(DomainError):
    """Parking tente d'allouer moins de places que celles déjà réservées
    sur un créneau : ces réservations confirmées ne doivent pas être
    perdues."""

    def __init__(self, allocated: int, booked: int):
        self.allocated = allocated
        self.booked = booked
        super().__init__(
            f"Impossible d'allouer {allocated} place(s) : {booked} place(s) déjà réservée(s) sur ce créneau"
        )


class ReservationNotFoundError(DomainError):
    def __init__(self, reservation_id: str):
        self.reservation_id = reservation_id
        super().__init__("Réservation introuvable")


class InvalidReservationStateError(DomainError):
    """La réservation n'est pas dans un état permettant l'opération demandée
    (ex. annuler une réservation qui n'est pas confirmée)."""


class ReservationIdGenerationError(DomainError):
    """Échec de génération d'un identifiant de réservation unique (voir
    ReservationService._generate_reservation_id)."""


class ExternalServiceError(DomainError):
    """Un service externe (Vehicles/Pricing/Payment) a échoué ou est injoignable."""
