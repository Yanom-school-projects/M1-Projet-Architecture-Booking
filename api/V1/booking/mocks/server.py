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

RATES = {
    "standard": Decimal("2.00"),
    "xl": Decimal("3.00"),
    "handicap": Decimal("2.00"),
    "electrique": Decimal("2.50"),
    "deux_roues": Decimal("1.00"),
}


class ResolveVehicleRequest(BaseModel):
    plate: str


@app.post("/vehicles/resolve")
def resolve_vehicle(payload: ResolveVehicleRequest):
    vehicle_id = hashlib.sha256(payload.plate.upper().encode()).hexdigest()[:16]
    return {"vehicle_id": vehicle_id}


class PricingRequest(BaseModel):
    place_type: str
    start_at: str
    end_at: str


@app.post("/pricing/reservation")
def price_reservation(payload: PricingRequest):
    start = datetime.fromisoformat(payload.start_at)
    end = datetime.fromisoformat(payload.end_at)
    hours = Decimal(str((end - start).total_seconds() / 3600))
    rate = RATES.get(payload.place_type, Decimal("2.00"))
    amount = (rate * hours).quantize(Decimal("0.01"))
    return {"amount": float(amount), "price_reference": "mock-grid-v1"}


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
