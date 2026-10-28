"""Implémentation HTTP du port PaymentPort, alignée sur le contrat du service
Payment (voir son Swagger : /docs).

- POST /payments répond 202 avec un statut PENDING ;
- le statut final (ACCEPTED ou REFUSED) s'obtient en interrogeant
  GET /payments/{payment_id} : Payment ne rappelle pas Booking.
- Les montants circulent en centimes (entier), pas en euros."""

import logging
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.domain.value_objects import PaymentAttempt
from app.ports.external_services import PaymentPort

from .wake_up import wake_up

logger = logging.getLogger("booking.payment")


def to_cents(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class HttpPaymentClient(PaymentPort):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def wake_up(self) -> None:
        await wake_up(self._base_url, self._timeout)

    async def create_payment(self, amount: Decimal, reference: str, idempotency_key: str) -> PaymentAttempt:
        body = {
            # Rejouer la même clé ne crée pas un second encaissement
            # côté Payment : elle doit rester stable pour une même
            # opération métier.
            "idempotency_key": idempotency_key,
            "amount": to_cents(amount),
            "currency": "EUR",
            "reference": {"type": "BOOKING", "id": reference},
            "source_service": "booking",
        }
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            try:
                resp = await client.post(f"{self._base_url}/payments", json=body)
            except httpx.TimeoutException:
                # Le paiement a pu être créé sans que la réponse arrive. Un
                # second essai avec la même clé renvoie ce paiement au lieu
                # d'en créer un autre.
                logger.warning("Délai dépassé chez Payment pour la réservation %s, nouvel essai", reference)
                resp = await client.post(f"{self._base_url}/payments", json=body)
            resp.raise_for_status()
            data = resp.json()
            return PaymentAttempt(payment_id=data["payment_id"], status=data["status"])

    async def get_payment(self, payment_id: str) -> PaymentAttempt:
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            resp = await client.get(f"{self._base_url}/payments/{payment_id}")
            resp.raise_for_status()
            data = resp.json()
            return PaymentAttempt(payment_id=data["payment_id"], status=data["status"])
