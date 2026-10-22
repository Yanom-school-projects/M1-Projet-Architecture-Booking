"""Port vers le service Parking, autorité sur le stock de places. Booking
lui demande combien de places de chaque type sont proposées à la
réservation, et s'en sert comme capacité de son calendrier."""

from abc import ABC, abstractmethod

from app.domain.enums import PlaceType


class ParkingPort(ABC):
    @abstractmethod
    async def get_booking_capacity(self, place_type: PlaceType) -> int:
        """Nombre de places de ce type proposées à la réservation."""
