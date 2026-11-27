"""Implémentation HTTP du port PricingPort, alignée sur le contrat du service
Pricing (voir son Swagger : /docs).

POST /quote attend une zone (le code du type de place, ex. `STANDARD`), le mode
`reserved` et une durée en minutes. Il renvoie le montant en euros (texte)
et un `quote_id`, que Booking conserve comme référence : GET /quotes/{id}
chez Pricing permet de retrouver la grille et sa version (traçabilité)."""

from datetime import datetime
from decimal import Decimal

from app.domain.value_objects import PriceQuote
from app.ports.external_services import PricingPort

from .http_client import http_client
from .wake_up import wake_up


class HttpPricingClient(PricingPort):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def wake_up(self) -> None:
        await wake_up(self._base_url, self._timeout)

    async def get_reservation_price(self, place_type: str, start_at: datetime, end_at: datetime) -> PriceQuote:
        duration_min = int((end_at - start_at).total_seconds() // 60)
        async with http_client(self._timeout, self._headers) as client:
            resp = await client.post(
                f"{self._base_url}/quote",
                json={"zone": place_type, "mode": "reserved", "duration_min": duration_min},
            )
            resp.raise_for_status()
            data = resp.json()
            # amount_eur arrive en texte ("2.50") : converti tel quel en
            # Decimal, sans passer par un float.
            return PriceQuote(amount=Decimal(data["amount_eur"]), reference=data["quote_id"])
