"""Implémentation HTTP du port PricingPort, alignée sur le contrat du service
Pricing (voir son Swagger : /docs).

POST /quote attend une zone (nom de Pricing pour le type de place), le mode
`reserved` et une durée en minutes. Il renvoie le montant en euros (texte)
et un `quote_id`, que Booking conserve comme référence : GET /quotes/{id}
chez Pricing permet de retrouver la grille et sa version (traçabilité)."""

from datetime import datetime
from decimal import Decimal

import httpx

from app.domain.value_objects import PriceQuote
from app.ports.external_services import PricingPort

# Types de place de Booking -> zones de Pricing.
PRICING_ZONES = {
    "standard": "standard",
    "xl": "xl",
    "handicap": "disabled",
    "electrique": "electric",
    "deux_roues": "two_wheels",
}


class HttpPricingClient(PricingPort):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._timeout = timeout

    async def get_reservation_price(self, place_type: str, start_at: datetime, end_at: datetime) -> PriceQuote:
        duration_min = int((end_at - start_at).total_seconds() // 60)
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            resp = await client.post(
                f"{self._base_url}/quote",
                json={"zone": PRICING_ZONES[place_type], "mode": "reserved", "duration_min": duration_min},
            )
            resp.raise_for_status()
            data = resp.json()
            # amount_eur arrive en texte ("2.50") : converti tel quel en
            # Decimal, sans passer par un float.
            return PriceQuote(amount=Decimal(data["amount_eur"]), reference=data["quote_id"])
