"""Traduction centralisée des exceptions métier en réponses HTTP. C'est la
seule frontière où une exception domain/ devient un code de statut — le
domaine et la couche application ne connaissent aucun code HTTP (voir
app/domain/exceptions.py)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    CapacityUnavailableError,
    ExternalServiceError,
    InvalidReservationStateError,
    InvalidSlotError,
    ReservationIdGenerationError,
    ReservationNotFoundError,
)

STATUS_CODES = {
    InvalidSlotError: 422,
    CapacityUnavailableError: 409,
    ReservationNotFoundError: 404,
    InvalidReservationStateError: 409,
    ReservationIdGenerationError: 500,
    ExternalServiceError: 502,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, status_code in STATUS_CODES.items():
        app.add_exception_handler(exc_type, _handler_for(status_code))


def _handler_for(status_code: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler
