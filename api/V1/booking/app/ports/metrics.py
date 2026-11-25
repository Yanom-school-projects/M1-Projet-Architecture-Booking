"""Port de mesure des opérations métier. Le domaine et l'application disent
QUOI compter (« une réservation vient d'être confirmée ») sans savoir
COMMENT c'est exposé : l'implémentation Prometheus vit dans
adapters/outbound/metrics. Remplacer Prometheus ne toucherait pas au métier.

Les noms d'opération et de résultat sont des constantes : un nombre fini de
valeurs, condition pour ne pas multiplier les séries côté Prometheus."""

from abc import ABC, abstractmethod


class Operation:
    RESERVATION_CREATE = "reservation_create"    # demande de réservation reçue
    RESERVATION_PAYMENT = "reservation_payment"  # issue du paiement d'une réservation
    RESERVATION_CANCEL = "reservation_cancel"    # annulation par le client
    ACCESS_CHECK = "access_check"                # vérification d'Access à la barrière
    CAPACITY_SYNC = "capacity_sync"              # synchro de capacité depuis Parking
    CAPACITY_UPDATE = "capacity_update"          # ajustement manuel d'un créneau


class Result:
    SUCCESS = "success"
    ERROR = "error"
    ACCEPTED = "accepted"   # paiement accepté → réservation confirmée
    REFUSED = "refused"     # paiement refusé → réservation en échec
    VALID = "valid"         # le véhicule a une réservation valable
    INVALID = "invalid"     # aucune réservation valable


class BusinessMetrics(ABC):
    @abstractmethod
    def record(self, operation: str, result: str) -> None: ...


class NoOpBusinessMetrics(BusinessMetrics):
    """Par défaut (tests, scripts) : ne mesure rien."""

    def record(self, operation: str, result: str) -> None:
        pass
