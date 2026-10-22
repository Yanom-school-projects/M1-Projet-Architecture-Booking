"""Implémentation HTTP du port PaymentPort. La réponse immédiate n'est
qu'un statut intermédiaire (souvent `pending`) : le statut final arrive plus
tard sur `callback_url` (voir adapters/inbound/http/routers/webhooks.py)."""

from decimal import Decimal

import httpx

from app.domain.value_objects import PaymentAttempt
from app.ports.external_services import PaymentPort


class HttpPaymentClient(PaymentPort):
    def __init__(self, base_url: str):
        self._base_url = base_url

    async def create_payment(
        self, amount: Decimal, reference: str, idempotency_key: str, callback_url: str
    ) -> PaymentAttempt:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self._base_url}/payments",
                json={
                    "amount": float(amount),
                    "reference": reference,
                    # rejouer le même idempotency_key ne doit pas créer un
                    # second encaissement côté Payment (exigence d'idempotence
                    # du cadrage).
                    "idempotency_key": idempotency_key,
                    "callback_url": callback_url,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return PaymentAttempt(payment_id=data["payment_id"], status=data["status"])
