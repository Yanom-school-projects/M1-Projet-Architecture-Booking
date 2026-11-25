"""Middleware ASGI : fixe l'identifiant de corrélation de chaque requête.

Reprend l'en-tête X-Correlation-ID envoyé par l'appelant (Access, le front,
un autre service), ou en génère un. Le renvoie dans l'en-tête de la réponse :
le client d'une création de réservation récupère ainsi l'identifiant de tout
le parcours."""

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.correlation import CORRELATION_HEADER, new_correlation_id, sanitize_correlation_id, set_correlation_id


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cid = sanitize_correlation_id(Headers(scope=scope).get(CORRELATION_HEADER)) or new_correlation_id()
        # Pas de reset en sortie : chaque requête s'exécute dans sa propre
        # tâche asyncio, la valeur ne fuit pas vers les autres. La garder
        # jusqu'au bout permet au log d'erreur d'uvicorn (exception non
        # gérée) de porter encore l'identifiant.
        set_correlation_id(cid)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[CORRELATION_HEADER] = cid
            await send(message)

        await self.app(scope, receive, send_with_header)
