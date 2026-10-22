"""Implémentations du port EventPublisher : une version de secours (log) et
une version réelle (RabbitMQ/CloudAMQP, consommée par Messages/Notification)."""

import json
import logging
from typing import Any, Mapping

import pika

from app.ports.event_publisher import EventPublisher

logger = logging.getLogger("booking.events")


class LoggingEventPublisher(EventPublisher):
    """Implémentation de secours : logge l'événement au lieu de le publier.
    Utilisée quand CLOUDAMQP_URL n'est pas configurée (dev sans bus réel)."""

    def publish(self, event_type: str, payload: Mapping[str, Any]) -> None:
        logger.info("event published type=%s payload=%s", event_type, dict(payload))


class RabbitMQEventPublisher(EventPublisher):
    """Publie sur l'exchange partagé du bus d'événements (CloudAMQP/RabbitMQ),
    consommé notamment par le service Messages/Notification.

    Routing key attendue par Notification, confirmée par leur équipe :
    `booking.confirmed` pour une réservation confirmée, `booking.cancelled`
    pour une annulation (voir ROUTING_KEYS). Le champ `event` du payload
    reste en MAJUSCULES_SNAKE_CASE (ex. `RESERVATION_CONFIRMED`), à l'image
    de leur exemple `ACCESS_ENTRY_DETECTED` — non confirmé explicitement,
    à vérifier si Notification se base dessus plutôt que sur la routing key.

    Une connexion AMQP est ouverte et refermée à chaque publication plutôt
    que maintenue en pool : les événements de Booking restent peu fréquents
    pour ce MVP (une confirmation ou une annulation par réservation) — à
    revoir si le volume augmente.
    """

    ROUTING_KEYS = {
        "reservation.confirmed": "booking.confirmed",
        "reservation.cancelled": "booking.cancelled",
    }

    def __init__(self, amqp_url: str, exchange: str):
        self._amqp_url = amqp_url
        self._exchange = exchange

    def publish(self, event_type: str, payload: Mapping[str, Any]) -> None:
        routing_key = self.ROUTING_KEYS.get(event_type, f"booking.{event_type}")
        body = {"event": event_type.upper().replace(".", "_"), **payload}

        connection = pika.BlockingConnection(pika.URLParameters(self._amqp_url))
        try:
            channel = connection.channel()
            # passive=True : vérifie que l'exchange existe sans tenter de le
            # (re)créer, pour ne pas se heurter à un mismatch de
            # configuration avec l'exchange déjà déclaré par l'équipe (406).
            channel.exchange_declare(exchange=self._exchange, passive=True)
            channel.basic_publish(
                exchange=self._exchange,
                routing_key=routing_key,
                body=json.dumps(body),
                properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
            )
            logger.info("event published exchange=%s routing_key=%s body=%s", self._exchange, routing_key, body)
        finally:
            connection.close()


def build_event_publisher(cloudamqp_url: str, exchange: str) -> EventPublisher:
    return RabbitMQEventPublisher(cloudamqp_url, exchange) if cloudamqp_url else LoggingEventPublisher()
