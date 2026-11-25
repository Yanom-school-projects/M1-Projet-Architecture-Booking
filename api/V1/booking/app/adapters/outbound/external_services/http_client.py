"""Client HTTP commun à tous les appels sortants (Vehicles, Pricing, Payment,
Parking, réveil) : ajoute l'en-tête X-Correlation-ID de la requête en cours,
pour que les services appelés puissent le reprendre dans leurs logs."""

from typing import Optional

import httpx

from app.correlation import CORRELATION_HEADER, get_correlation_id


async def _add_correlation_header(request: httpx.Request) -> None:
    # Lu au moment de l'envoi, pas à la création du client : c'est
    # l'identifiant courant de l'appel qui compte.
    cid = get_correlation_id()
    if cid:
        request.headers[CORRELATION_HEADER] = cid


def http_client(timeout: float, headers: Optional[dict] = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        headers=headers or {},
        event_hooks={"request": [_add_correlation_header]},
    )
