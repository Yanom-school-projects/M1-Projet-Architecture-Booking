"""Port de publication d'événements métier, consommés par le service
Messages/Notification. L'implémentation réelle (RabbitMQ) et la version de
secours (log) vivent dans adapters/outbound/messaging."""

from abc import ABC, abstractmethod
from typing import Any, Mapping


class EventPublisher(ABC):
    @abstractmethod
    def publish(self, event_type: str, payload: Mapping[str, Any]) -> None: ...
