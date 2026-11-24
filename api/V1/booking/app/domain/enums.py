"""Enums métier purs : aucune dépendance à un framework."""

import enum


class PlaceType(str, enum.Enum):
    """Code technique du type de place : c'est la valeur échangée avec les
    autres services (API, Parking, événements) et stockée en base. Le
    libellé affiché à l'utilisateur est donné par `label`."""

    STANDARD = "STANDARD"
    HANDICAPPED = "HANDICAPPED"
    ELECTRIC = "ELECTRIC"
    XL = "XL"
    TWO_WHEELS = "TWO_WHEELS"

    @property
    def label(self) -> str:
        return PLACE_TYPE_LABELS[self]


# Libellés destinés à l'utilisateur (front, e-mails de Notification).
PLACE_TYPE_LABELS = {
    PlaceType.STANDARD: "Standard",
    PlaceType.HANDICAPPED: "PMR",
    PlaceType.ELECTRIC: "Électrique",
    PlaceType.XL: "XL",
    PlaceType.TWO_WHEELS: "Deux-roues",
}


class ReservationStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"  # paiement demandé, statut final pas encore connu chez Payment
    CONFIRMED = "confirmed"  # paiement accepté, la réservation consomme la capacité
    CANCELLED = "cancelled"  # annulée par le client, capacité libérée (sans remboursement)
    FAILED = "failed"  # paiement refusé, capacité libérée
