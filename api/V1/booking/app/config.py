"""Configuration centralisée, lue depuis les variables d'environnement (ou un
fichier .env local). Les URLs des services dépendants pointent par défaut vers
les mocks locaux (voir mocks/server.py) : il suffit de les surcharger en
variables d'env pour brancher les vrais services de l'équipe, sans changer le
code."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./booking.db"

    vehicles_service_url: str = "http://localhost:9000/vehicles"
    pricing_service_url: str = "http://localhost:9000/pricing"
    payment_service_url: str = "http://localhost:9000/payment"

    # URL publique de Booking : transmise à Payment pour qu'il sache où
    # rappeler le webhook une fois le paiement traité.
    booking_public_url: str = "http://localhost:8000"
    payment_webhook_path: str = "/webhooks/payment"

    reservation_horizon_days: int = 30
    reservation_max_duration_hours: int = 24 * 7

    # Bus d'événements (CloudAMQP/RabbitMQ) vers le service Messages/Notification.
    # Vide par défaut : sans URL configurée, EventPublisher retombe sur un simple
    # log (voir app/events.py) plutôt que d'échouer au démarrage.
    cloudamqp_url: str = ""
    event_bus_exchange: str = "microservice-event-bus"


settings = Settings()
