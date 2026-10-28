"""Configuration centralisée, lue depuis les variables d'environnement (ou un
fichier .env local). Les URLs des services dépendants pointent par défaut vers
les mocks locaux (voir mocks/server.py) : il suffit de les surcharger en
variables d'env pour brancher les vrais services de l'équipe, sans changer le
code."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore" : une variable inconnue dans le .env ne doit pas
    # empêcher le service de démarrer.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./booking.db"

    vehicles_service_url: str = "http://localhost:9000/vehicles"
    pricing_service_url: str = "http://localhost:9000/pricing"
    payment_service_url: str = "http://localhost:9000/payment"
    # Booking lit chez Parking le nombre de places réservables par type
    # (vide = pas de synchronisation, la capacité vient de PUT /capacity).
    parking_service_url: str = ""
    parking_sync_interval_seconds: float = 3600.0

    # Clés envoyées dans l'en-tête X-API-Key à chaque service (vide = pas
    # d'en-tête). Jamais dans Git : à définir en variable d'environnement
    # (Render) ou dans le .env local.
    vehicles_api_key: str = ""
    pricing_api_key: str = ""
    payment_api_key: str = ""
    parking_api_key: str = ""

    # TEMPORAIRE : si Vehicles ne répond pas, Booking calcule lui-même un
    # identifiant (empreinte de la plaque, préfixe `tmp-`) au lieu de
    # renvoyer 502. Désactivé par défaut. Voir vehicles_fallback.py.
    vehicles_fallback_enabled: bool = False
    vehicles_fallback_secret: str = "booking-temporaire"

    # Payment ne rappelle pas Booking : c'est Booking qui interroge
    # GET /payments/{id} jusqu'au statut final (ACCEPTED ou REFUSED).
    payment_poll_interval_seconds: float = 5.0
    payment_poll_timeout_seconds: float = 180.0

    # Timeout des appels HTTP sortants. Large, car un service Render gratuit
    # en veille met ~30 s à se réveiller.
    http_timeout_seconds: float = 30.0

    reservation_horizon_days: int = 30
    reservation_max_duration_hours: int = 24 * 7

    # Bus d'événements (CloudAMQP/RabbitMQ) vers le service Messages/Notification.
    # Vide par défaut : sans URL configurée, EventPublisher retombe sur un simple
    # log (voir app/events.py) plutôt que d'échouer au démarrage.
    cloudamqp_url: str = ""
    event_bus_exchange: str = "microservice-event-bus"


settings = Settings()
