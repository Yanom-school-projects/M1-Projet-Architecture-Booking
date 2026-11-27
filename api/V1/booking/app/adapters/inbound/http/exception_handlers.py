"""Traduction centralisée des exceptions métier en réponses HTTP. C'est la
seule frontière où une exception domain/ devient un code de statut — le
domaine et la couche application ne connaissent aucun code HTTP (voir
app/domain/exceptions.py).

Chaque erreur renvoyée au client est aussi loguée, avec un niveau qui
dépend de sa gravité (voir _log_level)."""

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.correlation import get_correlation_id
from app.domain.exceptions import (
    CapacityBelowBookedError,
    CapacityUnavailableError,
    ExternalServiceError,
    InvalidReservationStateError,
    InvalidSlotError,
    ReservationIdGenerationError,
    ReservationNotFoundError,
)

logger = logging.getLogger("booking.http")

STATUS_CODES = {
    InvalidSlotError: 422,
    CapacityUnavailableError: 409,
    CapacityBelowBookedError: 409,
    ReservationNotFoundError: 404,
    InvalidReservationStateError: 409,
    ReservationIdGenerationError: 500,
    ExternalServiceError: 502,
}


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, status_code in STATUS_CODES.items():
        app.add_exception_handler(exc_type, _handler_for(status_code))
    app.add_exception_handler(RequestValidationError, _log_validation_error)
    app.add_exception_handler(Exception, _unexpected_error)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Erreur imprévue (bug, base injoignable...) : le détail complet va dans
    les logs, le client ne reçoit qu'un message générique et l'identifiant de
    corrélation pour retrouver la trace. Jamais de pile d'appels, de requête
    SQL ou de chemin de fichier dans la réponse."""
    logger.exception("%s %s -> 500 erreur inattendue", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du service Booking", "correlation_id": get_correlation_id()},
    )


def _log_level(status_code: int) -> int:
    """500 : erreur interne de Booking. 502 : panne d'un service appelé,
    déjà détaillée par le client HTTP concerné. 4xx : refus métier normal."""
    if status_code == 502:
        return logging.WARNING
    if status_code >= 500:
        return logging.ERROR
    return logging.INFO


def _handler_for(status_code: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        logger.log(
            _log_level(status_code),
            "%s %s -> %s %s : %s",
            request.method,
            request.url.path,
            status_code,
            type(exc).__name__,
            exc,
        )
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


async def _log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Requête mal formée (422 de FastAPI). On logue seulement le champ et le
    motif, jamais la valeur reçue : elle peut contenir une plaque ou un email."""
    fields = "; ".join(
        f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg', '')}" for err in exc.errors()
    )
    logger.info("%s %s -> 422 requête invalide : %s", request.method, request.url.path, fields)
    return await request_validation_exception_handler(request, exc)
