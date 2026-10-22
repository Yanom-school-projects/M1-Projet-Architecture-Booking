"""Mocks locaux de Vehicles / Pricing / Payment, le temps que les vrais
services de l'équipe soient disponibles. Remplaçables sans changer le code de
Booking : il suffit de pointer VEHICLES_SERVICE_URL / PRICING_SERVICE_URL /
PAYMENT_SERVICE_URL vers les vraies URLs (variables d'env, voir .env.example).

Lancement : uvicorn mocks.server:app --port 9000 --reload
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime
from decimal import Decimal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
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


class PaymentRequest(BaseModel):
    amount: float
    reference: str
    idempotency_key: str
    callback_url: str


async def _send_webhook(payment_id: str, status: str, reference: str, callback_url: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                callback_url,
                json={"payment_id": payment_id, "status": status, "reference": reference},
            )
        except httpx.HTTPError:
            logger.exception("Échec de l'appel du webhook de paiement vers %s", callback_url)


async def _confirm_payment_later(payment_id: str, reference: str, callback_url: str) -> None:
    # await asyncio.sleep(1)  # simule le traitement asynchrone du paiement
    payment = PAYMENTS[payment_id]
    if payment["status"] != "pending":
        return  # déjà tranché manuellement via /force-status, on n'écrase pas
    payment["status"] = "paid"
    await _send_webhook(payment_id, "paid", reference, callback_url)


async def _confirm_refund_later(payment_id: str, reference: str, callback_url: str) -> None:
    # await asyncio.sleep(1)  # traitement asynchrone du remboursement, plus rapide qu'un paiement
    payment = PAYMENTS[payment_id]
    if payment["status"] != "pending":
        return
    payment["status"] = "refunded"
    await _send_webhook(payment_id, "refunded", reference, callback_url)


@app.post("/payment/payments")
def create_payment(payload: PaymentRequest, background_tasks: BackgroundTasks):
    """Convention de test pour simuler un remboursement (le vrai contrat est
    à valider avec le service Payment réel) : si un paiement `paid` existe
    déjà pour cette `reference` et que le nouveau montant demandé est
    différent, on interprète l'appel comme une demande d'ajustement de prix
    et on rembourse la différence plutôt que de créer un nouvel encaissement."""
    if payload.idempotency_key in IDEMPOTENCY:
        payment_id = IDEMPOTENCY[payload.idempotency_key]
        return {"payment_id": payment_id, "status": PAYMENTS[payment_id]["status"]}

    existing_paid = next(
        (p for p in PAYMENTS.values() if p["reference"] == payload.reference and p["status"] == "paid"),
        None,
    )
    if existing_paid is not None and Decimal(str(payload.amount)) != Decimal(str(existing_paid["amount"])):
        payment_id = str(uuid.uuid4())
        PAYMENTS[payment_id] = {
            "status": "pending",
            "amount": payload.amount,
            "reference": payload.reference,
            "callback_url": payload.callback_url,
        }
        IDEMPOTENCY[payload.idempotency_key] = payment_id
        existing_paid["amount"] = payload.amount  # le paiement d'origine reflète désormais le nouveau montant

        background_tasks.add_task(_confirm_refund_later, payment_id, payload.reference, payload.callback_url)
        return {"payment_id": payment_id, "status": "pending"}

    payment_id = str(uuid.uuid4())
    PAYMENTS[payment_id] = {
        "status": "pending",
        "amount": payload.amount,
        "reference": payload.reference,
        "callback_url": payload.callback_url,
    }
    IDEMPOTENCY[payload.idempotency_key] = payment_id

    background_tasks.add_task(_confirm_payment_later, payment_id, payload.reference, payload.callback_url)

    return {"payment_id": payment_id, "status": "pending"}


@app.get("/payment/payments/{payment_id}")
def get_payment(payment_id: str):
    return PAYMENTS.get(payment_id, {"status": "unknown"})


class ForcePaymentStatusRequest(BaseModel):
    status: str  # "paid" | "refused" | "cancelled" | "refunded"


@app.post("/payment/payments/{payment_id}/force-status")
async def force_payment_status(payment_id: str, payload: ForcePaymentStatusRequest):
    """Outil de test uniquement : déclenche immédiatement le webhook avec le
    statut demandé, sans attendre les 3s de confirmation automatique. Permet
    de tester les branches refused/cancelled côté Booking, que le flux
    automatique (toujours `paid`) ne peut pas exercer."""
    payment = PAYMENTS.get(payment_id)
    if payment is None:
        raise HTTPException(404, "Paiement inconnu")

    payment["status"] = payload.status
    await _send_webhook(payment_id, payload.status, payment["reference"], payment["callback_url"])
    return {"payment_id": payment_id, "status": payload.status}
