"""Implémentation HTTP du port PaymentPort, alignée sur le contrat du service
Payment (voir son Swagger : /docs).

- POST /payments répond 202 avec un statut PENDING ;
- le statut final (ACCEPTED ou REFUSED) s'obtient en interrogeant
  GET /payments/{payment_id} : Payment ne rappelle pas Booking.
- Les montants circulent en centimes (entier), pas en euros."""

import logging
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.domain.exceptions import PaymentOutcomeUnknownError, PaymentRejectedError
from app.domain.value_objects import PaymentAttempt
from app.ports.external_services import PaymentPort

from .http_client import http_client
from .wake_up import wake_up

logger = logging.getLogger("booking.payment")

# Lecture des 4xx de POST /payments, confirmée par l'équipe Payment. Un 4xx
# dit que CET appel n'a rien créé, pas qu'aucun paiement n'existe pour la clé :
# un envoi précédent (dont la réponse s'est perdue) a pu le créer.
# - 422 : corps invalide, rejeté dès le premier envoi -> refus certain.
# - 401 : clé API absente ou invalide (configuration) -> issue inconnue + alerte.
# - 409 : la clé désigne déjà un paiement avec un autre montant, une autre
#   référence ou un autre service, peut-être ACCEPTED -> anomalie, jamais
#   failed, alerte. Ne doit pas arriver : le montant renvoyé est celui
#   enregistré sur la réservation, jamais recalculé.
# - 400, 403, 404, 408, 429 : jamais renvoyés par Payment. Tout autre code
#   est traité comme une issue inconnue, le cas sans risque de double débit.
_DEFINITIVE_REFUSALS = {422}
_ALERTS = {
    401: "clé API refusée par Payment, vérifier PAYMENT_API_KEY",
    409: "ANOMALIE : la clé désigne déjà un paiement avec un autre corps (montant, référence ou service)",
}


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
        try:
            async with http_client(self._timeout, self._headers) as client:
                try:
                    resp = await client.post(f"{self._base_url}/payments", json=body)
                except httpx.TimeoutException:
                    # Le paiement a pu être créé sans que la réponse arrive. Un
                    # second essai avec la même clé renvoie ce paiement au lieu
                    # d'en créer un autre.
                    logger.warning(
                        "Délai dépassé chez Payment (clé %s), nouvel essai avec la même clé", idempotency_key
                    )
                    resp = await client.post(f"{self._base_url}/payments", json=body)
                if resp.status_code in _DEFINITIVE_REFUSALS:
                    logger.error(
                        "Payment refuse la demande (clé %s) : %s %s", idempotency_key, resp.status_code, resp.text[:200]
                    )
                    raise PaymentRejectedError(f"Demande de paiement refusée par Payment ({resp.status_code})")
                if resp.status_code in _ALERTS:
                    # Un paiement peut exister : la réservation reste en attente.
                    logger.error(
                        "%s (clé %s, montant %s centimes) : %s",
                        _ALERTS[resp.status_code],
                        idempotency_key,
                        body["amount"],
                        resp.text[:200],
                    )
                resp.raise_for_status()
                data = resp.json()
                return PaymentAttempt(payment_id=data["payment_id"], status=data["status"])
        except PaymentRejectedError:
            raise
        except Exception as exc:
            # Timeout répété, coupure réseau, 5xx, réponse illisible : la
            # demande a pu aboutir chez Payment. On ne conclut pas à l'échec.
            logger.warning("Issue de la demande de paiement inconnue (clé %s) : %r", idempotency_key, exc)
            raise PaymentOutcomeUnknownError("Issue de la demande de paiement inconnue") from exc

    async def get_payment(self, payment_id: str) -> PaymentAttempt:
        async with http_client(self._timeout, self._headers) as client:
            resp = await client.get(f"{self._base_url}/payments/{payment_id}")
            resp.raise_for_status()
            data = resp.json()
            return PaymentAttempt(payment_id=data["payment_id"], status=data["status"])
