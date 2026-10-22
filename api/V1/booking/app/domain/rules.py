"""Règles métier pures : aucune dépendance à une base de données, un service
externe ou l'heure système directement (elle est injectée par l'appelant,
pour que ces fonctions restent testables sans mock)."""

from datetime import datetime, timedelta

from .exceptions import InvalidSlotError


def validate_slot(
    start_at: datetime,
    end_at: datetime,
    *,
    now: datetime,
    horizon_days: int,
    max_duration_hours: int,
) -> None:
    """Règles du cadrage métier : créneaux sur heures pleines, horizon de
    réservation, durée max alignée sur le plafond de stationnement."""
    if (start_at.minute, start_at.second, start_at.microsecond) != (0, 0, 0):
        raise InvalidSlotError("start_at doit être aligné sur une heure pleine")
    if (end_at.minute, end_at.second, end_at.microsecond) != (0, 0, 0):
        raise InvalidSlotError("end_at doit être aligné sur une heure pleine")
    if end_at <= start_at:
        raise InvalidSlotError("end_at doit être postérieur à start_at")

    current_hour = now.replace(minute=0, second=0, microsecond=0)
    if start_at < current_hour:
        raise InvalidSlotError("Le créneau demandé est déjà passé")

    horizon = current_hour + timedelta(days=horizon_days)
    if start_at > horizon:
        raise InvalidSlotError(f"Créneau au-delà de l'horizon de réservation ({horizon_days} jours)")

    if end_at - start_at > timedelta(hours=max_duration_hours):
        raise InvalidSlotError(f"Durée de réservation supérieure au maximum autorisé ({max_duration_hours}h)")


def hour_slots(start_at: datetime, end_at: datetime) -> list[datetime]:
    """Découpe [start_at, end_at) en heures pleines : une réservation de
    plusieurs heures consomme une unité de capacité sur chacune d'elles."""
    slots = []
    current = start_at
    while current < end_at:
        slots.append(current)
        current += timedelta(hours=1)
    return slots
