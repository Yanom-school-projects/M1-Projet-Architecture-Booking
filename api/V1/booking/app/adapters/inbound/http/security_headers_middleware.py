"""Middleware ASGI : en-têtes de sécurité HTTP sur chaque réponse.

Booking ne sert que du JSON (plus la page Swagger) : ces en-têtes empêchent
le navigateur de réinterpréter une réponse (nosniff), de l'afficher dans un
cadre d'un autre site (clickjacking) et de transmettre l'URL appelée à un
site tiers. Les réponses de l'API, qui peuvent contenir un e-mail, ne
doivent pas non plus être gardées en cache."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str):
        self.app = app
        self.api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        no_store = scope["path"].startswith(self.api_prefix)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if no_store:
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)
