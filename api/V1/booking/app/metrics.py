"""Métriques Prometheus du service Booking.

Toutes les métriques sont déclarées ici, une seule fois au chargement du
module (prometheus_client refuse deux métriques du même nom). Le reste du
code se contente de les importer et d'appeler .labels(...).inc().

Règle sur les labels : uniquement des valeurs en nombre FINI (méthode,
modèle de route, code HTTP...). Jamais un id de réservation, une plaque ou
une URL brute : chaque valeur distincte crée une nouvelle série temporelle."""

from prometheus_client import Counter

# Trafic HTTP : une série par (méthode, route, code, issue).
# « outcome » vaut success (< 400) ou error (>= 400) pour filtrer simplement
# en PromQL : sum(rate(http_requests_total{outcome="error"}[1m])).
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Requêtes HTTP traitées par le service",
    ["method", "route", "status", "outcome"],
)

# Opérations métier : « operation » nomme l'action, « result » son issue.
PARKING_OPERATIONS = Counter(
    "parking_operations_total",
    "Opérations métier du service Booking",
    ["service", "operation", "result"],
)
