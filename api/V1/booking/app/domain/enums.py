"""Enums métier purs : aucune dépendance à un framework."""

import enum


class PlaceType(str, enum.Enum):
    STANDARD = "standard"
    XL = "xl"
    HANDICAP = "handicap"
    ELECTRIQUE = "electrique"
    DEUX_ROUES = "deux_roues"


class ReservationStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"  # paiement demandé, statut final pas encore connu chez Payment
    CONFIRMED = "confirmed"  # paiement accepté, la réservation consomme la capacité
    CANCELLED = "cancelled"  # annulée par le client, capacité libérée (sans remboursement)
    FAILED = "failed"  # paiement refusé, capacité libérée
