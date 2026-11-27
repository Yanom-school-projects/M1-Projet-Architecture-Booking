"""Métriques Prometheus du service Booking.

Toutes les métriques sont déclarées ici, une seule fois au chargement du
module (prometheus_client refuse deux métriques du même nom). Le reste du
code se contente de les importer et d'appeler .labels(...).inc().

Règle sur les labels : uniquement des valeurs en nombre FINI (méthode,
modèle de route, code HTTP...). Jamais un id de réservation, une plaque ou
une URL brute : chaque valeur distincte crée une nouvelle série temporelle."""

from prometheus_client import Counter, Histogram

# Trafic HTTP : une série par (méthode, route, code, issue).
# « outcome » vaut success (< 400) ou error (>= 400) pour filtrer simplement
# en PromQL : sum(rate(http_requests_total{outcome="error"}[1m])).
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Requêtes HTTP traitées par le service",
    ["method", "route", "status", "outcome"],
)

# Durée de traitement des requêtes, en secondes, par (méthode, route) : sans le
# code HTTP pour limiter le nombre de séries. Seuils élargis au-delà de 10 s :
# une création de réservation attend Vehicles, Pricing et Payment, qui mettent
# 30 à 60 s à se réveiller sur Render gratuit (timeout à 120 s).
# Latence p95 en PromQL :
# histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Durée de traitement des requêtes HTTP (secondes)",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)

# Opérations métier : « operation » nomme l'action, « result » son issue.
PARKING_OPERATIONS = Counter(
    "parking_operations_total",
    "Opérations métier du service Booking",
    ["service", "operation", "result"],
)
