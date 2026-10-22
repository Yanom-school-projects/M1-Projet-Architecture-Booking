"""Enums métier purs : aucune dépendance à un framework."""

import enum


class PlaceType(str, enum.Enum):
    STANDARD = "standard"
    XL = "xl"
    HANDICAP = "handicap"
    ELECTRIQUE = "electrique"
    DEUX_ROUES = "deux_roues"


class ReservationStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"  # paiement demandé, en attente du callback de Payment
    CONFIRMED = "confirmed"  # paiement reçu, la réservation consomme la capacité
    CANCELLATION_PENDING = "cancellation_pending"  # annulation demandée, remboursement en cours chez Payment
    CANCELLED = "cancelled"  # remboursement confirmé, réservation annulée
    FAILED = "failed"  # paiement refusé/annulé, capacité libérée
