"""Mocks locaux de Vehicles / Pricing / Payment, le temps que les vrais
services de l'équipe soient disponibles. Remplaçables sans changer le code de
Booking : il suffit de pointer VEHICLES_SERVICE_URL / PRICING_SERVICE_URL /
PAYMENT_SERVICE_URL vers les vraies URLs (variables d'env, voir .env.example).

Lancement : uvicorn mocks.server:app --port 9000 --reload
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("booking.mocks")
app = FastAPI(title="Mocks: Vehicles / Pricing / Payment")

# Tarifs horaires "reserved" du vrai Pricing, par zone.
RATES = {
    "standard": Decimal("2.50"),
    "xl": Decimal("4.00"),
    "disabled": Decimal("1.25"),
    "electric": Decimal("3.00"),
    "two_wheels": Decimal("0.80"),
}


class ResolveVehicleRequest(BaseModel):
    plate: str


@app.post("/vehicles/resolve")
def resolve_vehicle(payload: ResolveVehicleRequest):
    vehicle_id = hashlib.sha256(payload.plate.upper().encode()).hexdigest()[:16]
    return {"vehicle_id": vehicle_id}


class QuoteRequest(BaseModel):
    """Même contrat que le vrai service Pricing."""

    zone: str
    mode: str  # "reserved" | "walk_in"
    duration_min: int


@app.post("/pricing/quote", status_code=201)
def quote(payload: QuoteRequest):
    if payload.zone not in RATES:
        raise HTTPException(404, {"code": "ZONE_NOT_FOUND", "message": payload.zone})
    hours = -(-payload.duration_min // 60)  # toute heure entamée est due
    amount = (RATES[payload.zone] * hours).quantize(Decimal("0.01"))
    return {
        "quote_id": str(uuid.uuid4()),
        "grid_id": "mock-grid",
        "grid_version": 1,
        "amount_eur": str(amount),
        "currency": "EUR",
        "breakdown": {"zone": payload.zone, "mode": payload.mode, "duration_min": payload.duration_min},
        "computed_at": datetime.utcnow().isoformat() + "Z",
    }


PAYMENTS: dict[str, dict] = {}
IDEMPOTENCY: dict[str, str] = {}

# Le vrai Payment tranche en 15-30 s ; le mock va plus vite pour les tests.
MOCK_SETTLE_SECONDS = 5


class PaymentReference(BaseModel):
    type: str  # "BOOKING" | "PARKING_EXIT"
    id: str


class PaymentRequest(BaseModel):
    """Même contrat que le vrai service Payment (montant en centimes)."""

    idempotency_key: str
    amount: int
    currency: str = "EUR"
    reference: PaymentReference
    source_service: str


def _payment_view(payment_id: str) -> dict:
    payment = PAYMENTS[payment_id]
    if payment["status"] == "PENDING" and time.monotonic() - payment["created"] >= MOCK_SETTLE_SECONDS:
        payment["status"] = "ACCEPTED"
    return {
        "payment_id": payment_id,
        "status": payment["status"],
        "amount": payment["amount"],
        "currency": payment["currency"],
        "reference": payment["reference"],
        "source_service": payment["source_service"],
    }


@app.post("/payment/payments", status_code=202)
def create_payment(payload: PaymentRequest):
    """Idempotent : la même clé renvoie le même paiement. Le paiement passe
    de PENDING à ACCEPTED après quelques secondes (à la lecture)."""
    if payload.idempotency_key in IDEMPOTENCY:
        return _payment_view(IDEMPOTENCY[payload.idempotency_key])

    payment_id = str(uuid.uuid4())
    PAYMENTS[payment_id] = {
        "status": "PENDING",
        "amount": payload.amount,
        "currency": payload.currency,
        "reference": payload.reference.model_dump(),
        "source_service": payload.source_service,
        "created": time.monotonic(),
    }
    IDEMPOTENCY[payload.idempotency_key] = payment_id
    return _payment_view(payment_id)


@app.get("/payment/payments/{payment_id}")
def get_payment(payment_id: str):
    if payment_id not in PAYMENTS:
        raise HTTPException(404, "Paiement inconnu")
    return _payment_view(payment_id)


class ForcePaymentStatusRequest(BaseModel):
    status: str  # "ACCEPTED" | "REFUSED"


@app.post("/payment/payments/{payment_id}/force-status")
def force_payment_status(payment_id: str, payload: ForcePaymentStatusRequest):
    """Outil de test propre au mock (n'existe pas dans le vrai Payment) :
    fixe le statut final, par exemple REFUSED pour tester l'échec de paiement."""
    if payment_id not in PAYMENTS:
        raise HTTPException(404, "Paiement inconnu")
    PAYMENTS[payment_id]["status"] = payload.status
    return _payment_view(payment_id)
