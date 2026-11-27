"""Schémas Pydantic : forme des requêtes/réponses HTTP. Concern propre à cet
adaptateur — le domaine et l'application ne les connaissent pas. Ce sont ces
modèles (champs, types, descriptions) qui alimentent directement la
documentation Swagger générée par FastAPI."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import PlaceType, ReservationStatus


def to_utc_naive(value: datetime) -> datetime:
    """Booking stocke et compare toutes ses dates en UTC, sans fuseau.
    Une date reçue avec un fuseau (ex. `+02:00`) est convertie en UTC ; une
    date sans fuseau est considérée comme déjà en UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def mark_utc(value: datetime) -> datetime:
    """En sortie, rend l'UTC explicite (suffixe `Z`) pour les clients."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# Date en entrée : avec ou sans fuseau, ramenée en UTC.
UtcDatetime = Annotated[datetime, AfterValidator(to_utc_naive)]
# Date en sortie : toujours affichée en UTC.
UtcDatetimeOut = Annotated[datetime, AfterValidator(mark_utc)]


class AvailabilityResponse(BaseModel):
    """Résultat d'une recherche de disponibilité sur un créneau donné."""

    place_type: PlaceType = Field(..., description="Type de place recherché.")
    start_at: UtcDatetimeOut = Field(..., description="Début du créneau en UTC (heure pleine, inclus).")
    end_at: UtcDatetimeOut = Field(..., description="Fin du créneau en UTC (heure pleine, exclus).")
    available: bool = Field(..., description="True si au moins une place est libre sur tout le créneau.")
    min_free_capacity: int = Field(
        ..., description="Nombre minimum de places libres observé sur les heures du créneau (le facteur limitant)."
    )


class ReservationCreateRequest(BaseModel):
    """Demande de réservation envoyée par le client (via le front)."""

    vehicle_plate: str = Field(
        ...,
        # Lettres, chiffres, espaces et tirets : couvre les formats français
        # (AB-123-CD, 1234 AB 75) et la plupart des plaques étrangères.
        min_length=2,
        max_length=20,
        pattern=r"^[A-Za-z0-9 -]+$",
        description="Plaque du véhicule. Résolue en identifiant pseudonymisé auprès du service Vehicles "
        "avant d'être stockée : la plaque réelle ne transite pas au-delà de cet appel.",
        examples=["AB-123-CD"],
    )
    email: EmailStr = Field(
        ..., description="Email du client, utilisé par Messages/Notification pour la confirmation de réservation."
    )
    place_type: PlaceType = Field(..., description="Type de place souhaité.")
    start_at: UtcDatetime = Field(
        ...,
        description="Début du créneau, aligné sur une heure pleine. Sans fuseau, la date est lue comme de l'UTC.",
        examples=["2026-11-02T14:00:00+01:00"],
    )
    end_at: UtcDatetime = Field(
        ...,
        description="Fin du créneau, aligné sur une heure pleine. Sans fuseau, la date est lue comme de l'UTC.",
        examples=["2026-11-02T16:00:00+01:00"],
    )


class ReservationResponse(BaseModel):
    """État courant d'une réservation."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="Code de réservation à 6 chiffres, à communiquer par le client au parking.",
        examples=["482913"],
    )
    vehicle_id: str = Field(..., description="Identifiant pseudonymisé du véhicule (jamais la plaque réelle).")
    email: EmailStr = Field(..., description="Email du client pour cette réservation.")
    place_type: PlaceType = Field(..., description="Type de place réservé.")
    start_at: UtcDatetimeOut = Field(..., description="Début du créneau réservé (UTC).")
    end_at: UtcDatetimeOut = Field(..., description="Fin du créneau réservé (UTC).")
    status: ReservationStatus = Field(..., description="Statut courant de la réservation.")
    price_amount: Optional[float] = Field(
        None, description="Montant calculé par Pricing pour ce créneau, une fois connu."
    )
    price_reference: Optional[str] = Field(
        None, description="Référence de la grille tarifaire utilisée par Pricing (traçabilité)."
    )
    payment_id: Optional[str] = Field(None, description="Identifiant du paiement associé, côté service Payment.")


class ValidReservation(BaseModel):
    """Réservation qui couvre l'instant vérifié. Sans l'e-mail du client :
    Access n'en a pas besoin pour décider de l'entrée."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Code de réservation à 6 chiffres.", examples=["482913"])
    place_type: PlaceType = Field(..., description="Type de place réservé, à attribuer à l'entrée.")
    start_at: UtcDatetimeOut = Field(..., description="Début du créneau réservé (UTC).")
    end_at: UtcDatetimeOut = Field(..., description="Fin du créneau réservé (UTC).")


class ReservationCheckResponse(BaseModel):
    """Réponse à Access : le véhicule a-t-il une réservation valable à cet instant ?"""

    vehicle_id: str = Field(..., description="Identifiant pseudonymisé vérifié.")
    at: UtcDatetimeOut = Field(..., description="Instant vérifié (UTC).")
    valid: bool = Field(..., description="True si au moins une réservation confirmée couvre cet instant.")
    reservations: list[ValidReservation] = Field(
        ..., description="Réservations confirmées couvrant cet instant (vide si `valid` est false)."
    )


class CapacityAllocationRequest(BaseModel):
    """Nombre de places réservables à fixer pour le créneau désigné dans l'URL."""

    allocated: int = Field(
        ..., ge=0, description="Nombre total de places de ce type allouées à Booking sur ce créneau."
    )


class CapacitySlotResponse(BaseModel):
    """État d'un créneau horaire de capacité réservable."""

    model_config = ConfigDict(from_attributes=True)

    place_type: PlaceType = Field(..., description="Type de place concerné.")
    slot_start: UtcDatetimeOut = Field(..., description="Début du créneau d'une heure (UTC).")
    allocated: int = Field(..., description="Places de ce type mises à disposition de Booking sur ce créneau.")
    booked: int = Field(..., description="Places déjà réservées sur ce créneau.")
