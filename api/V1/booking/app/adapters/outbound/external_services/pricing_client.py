"""Implémentation HTTP du port PricingPort. Pricing renvoie aussi la
référence de la grille tarifaire utilisée, à conserver pour la traçabilité."""

from datetime import datetime
from decimal import Decimal

import httpx

from app.domain.value_objects import PriceQuote
from app.ports.external_services import PricingPort


class HttpPricingClient(PricingPort):
    def __init__(self, base_url: str):
        self._base_url = base_url

    async def get_reservation_price(self, place_type: str, start_at: datetime, end_at: datetime) -> PriceQuote:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self._base_url}/reservation",
                json={
                    "place_type": place_type,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # amount voyage en JSON comme un nombre (float), converti via str()
            # plutôt que Decimal(float) directement pour éviter les artefacts
            # de précision binaire (ex. Decimal(2.1) donnant 2.099999...).
            return PriceQuote(amount=Decimal(str(data["amount"])), reference=data["price_reference"])
