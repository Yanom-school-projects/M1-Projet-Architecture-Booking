"""Objets de valeur retournés par les ports externes (Pricing, Payment) —
des structures typées plutôt que des dicts bruts, pour que la couche
application ne manipule que du vocabulaire métier, jamais la forme JSON
d'une réponse HTTP d'un service tiers."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PriceQuote:
    amount: Decimal
    reference: str


@dataclass(frozen=True)
class PaymentAttempt:
    payment_id: str
    status: str
