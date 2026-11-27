"""Règles métier pures : aucune dépendance à une base de données, un service
externe ou l'heure système directement (elle est injectée par l'appelant,
pour que ces fonctions restent testables sans mock).

Unité de temps : le quart d'heure (v2.7.0). Un créneau commence et finit sur
:00, :15, :30 ou :45, et la capacité est comptée par quart d'heure. Écart
assumé avec le cadrage métier (tranches d'une heure), aligné sur la
facturation de Pricing, elle aussi au quart d'heure."""

from datetime import datetime, timedelta

from .exceptions import InvalidSlotError

SLOT_MINUTES = 15
SLOT = timedelta(minutes=SLOT_MINUTES)


def is_slot_aligned(value: datetime) -> bool:
    """Vrai si `value` tombe pile sur un quart d'heure (:00, :15, :30, :45)."""
    return value.minute % SLOT_MINUTES == 0 and value.second == 0 and value.microsecond == 0


def slot_floor(value: datetime) -> datetime:
    """Début du quart d'heure qui contient `value` (9 h 25 -> 9 h 15)."""
    return value.replace(minute=value.minute - value.minute % SLOT_MINUTES, second=0, microsecond=0)


def validate_slot(
    start_at: datetime,
    end_at: datetime,
    *,
    now: datetime,
    horizon_days: int,
    max_duration_hours: int,
) -> None:
    """Créneau sur des quarts d'heure, horizon de réservation, durée max
    alignée sur le plafond de stationnement."""
    if not is_slot_aligned(start_at):
        raise InvalidSlotError("start_at doit tomber sur un quart d'heure (:00, :15, :30 ou :45)")
    if not is_slot_aligned(end_at):
        raise InvalidSlotError("end_at doit tomber sur un quart d'heure (:00, :15, :30 ou :45)")
    if end_at <= start_at:
        raise InvalidSlotError("end_at doit être postérieur à start_at")

    # Le quart d'heure en cours reste réservable.
    current_slot = slot_floor(now)
    if start_at < current_slot:
        raise InvalidSlotError("Le créneau demandé est déjà passé")

    horizon = current_slot + timedelta(days=horizon_days)
    if start_at > horizon:
        raise InvalidSlotError(f"Créneau au-delà de l'horizon de réservation ({horizon_days} jours)")

    if end_at - start_at > timedelta(hours=max_duration_hours):
        raise InvalidSlotError(f"Durée de réservation supérieure au maximum autorisé ({max_duration_hours}h)")


def slot_starts(start_at: datetime, end_at: datetime) -> list[datetime]:
    """Découpe [start_at, end_at) en quarts d'heure : une réservation consomme
    une unité de capacité sur chacun d'eux (7 h 45 - 9 h -> 7 h 45, 8 h, 8 h 15, 8 h 30, 8 h 45)."""
    slots = []
    current = start_at
    while current < end_at:
        slots.append(current)
        current += SLOT
    return slots
