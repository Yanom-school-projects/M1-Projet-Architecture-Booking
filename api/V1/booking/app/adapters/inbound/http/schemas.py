"""Schémas Pydantic : forme des requêtes/réponses HTTP. Concern propre à cet
adaptateur — le domaine et l'application ne les connaissent pas. Ce sont ces
modèles (champs, types, descriptions) qui alimentent directement la
documentation Swagger générée par FastAPI."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import PlaceType, ReservationStatus


class AvailabilityResponse(BaseModel):
    """Résultat d'une recherche de disponibilité sur un créneau donné."""

    place_type: PlaceType = Field(..., description="Type de place recherché.")
    start_at: datetime = Field(..., description="Début du créneau (heure pleine, inclus).")
    end_at: datetime = Field(..., description="Fin du créneau (heure pleine, exclus).")
    available: bool = Field(..., description="True si au moins une place est libre sur tout le créneau.")
    min_free_capacity: int = Field(
        ..., description="Nombre minimum de places libres observé sur les heures du créneau (le facteur limitant)."
    )


class ReservationCreateRequest(BaseModel):
    """Demande de réservation envoyée par le client (via le front)."""

    vehicle_plate: str = Field(
        ...,
        description="Plaque du véhicule. Résolue en identifiant pseudonymisé auprès du service Vehicles "
        "avant d'être stockée : la plaque réelle ne transite pas au-delà de cet appel.",
        examples=["AB-123-CD"],
    )
    email: EmailStr = Field(
        ..., description="Email du client, utilisé par Messages/Notification pour la confirmation de réservation."
    )
    place_type: PlaceType = Field(..., description="Type de place souhaité.")
    start_at: datetime = Field(..., description="Début du créneau, aligné sur une heure pleine.")
    end_at: datetime = Field(..., description="Fin du créneau, aligné sur une heure pleine.")


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
    start_at: datetime = Field(..., description="Début du créneau réservé.")
    end_at: datetime = Field(..., description="Fin du créneau réservé.")
    status: ReservationStatus = Field(..., description="Statut courant de la réservation.")
    price_amount: Optional[float] = Field(
        None, description="Montant calculé par Pricing pour ce créneau, une fois connu."
    )
    price_reference: Optional[str] = Field(
        None, description="Référence de la grille tarifaire utilisée par Pricing (traçabilité)."
    )
    payment_id: Optional[str] = Field(None, description="Identifiant du paiement associé, côté service Payment.")


class CapacityAllocationRequest(BaseModel):
    """Allocation de capacité réservable pour un créneau, poussée par le service Parking."""

    place_type: PlaceType = Field(..., description="Type de place concerné.")
    slot_start: datetime = Field(..., description="Heure pleine du créneau concerné.")
    allocated: int = Field(
        ..., ge=0, description="Nombre total de places de ce type allouées à Booking sur ce créneau."
    )
