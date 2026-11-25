"""Identifiant de corrélation (en-tête X-Correlation-ID) : relie dans les logs
de tous les services les étapes d'un même parcours, de la création d'une
réservation jusqu'à la notification envoyée par Messages.

L'identifiant courant vit dans un ContextVar : chaque requête HTTP (et chaque
tâche asyncio qu'elle lance) a le sien, sans avoir à le passer en paramètre.
Il est posé par le middleware HTTP entrant, puis relu par :
- le filtre de logging (colonne correlation_id de chaque ligne) ;
- les clients HTTP sortants (en-tête X-Correlation-ID) ;
- le publisher RabbitMQ (propriété correlation_id et en-tête du message).

Une réservation garde l'identifiant de la requête qui l'a créée (stocké en
base) : ReservationService le remet en place avant chaque étape ultérieure
(confirmation, échec, annulation), même déclenchée par une autre requête."""

import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

CORRELATION_HEADER = "X-Correlation-ID"

# Reçu d'un autre service : on refuse ce qui pourrait polluer les logs
# (retours à la ligne, valeurs démesurées) et on en génère un nouveau.
_VALID_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def get_correlation_id() -> Optional[str]:
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    _correlation_id.set(correlation_id)


def sanitize_correlation_id(value: Optional[str]) -> Optional[str]:
    """Renvoie la valeur reçue si elle est acceptable, sinon None."""
    return value if value and _VALID_ID.match(value) else None


@contextmanager
def correlation_scope(correlation_id: Optional[str] = None) -> Iterator[str]:
    """Utilise `correlation_id` le temps du bloc. Sans valeur, garde
    l'identifiant courant, ou en génère un s'il n'y en a pas."""
    cid = correlation_id or get_correlation_id() or new_correlation_id()
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)
