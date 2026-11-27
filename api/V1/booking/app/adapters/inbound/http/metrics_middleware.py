"""Middleware ASGI : compte chaque requête HTTP dans http_requests_total et
mesure sa durée dans http_request_duration_seconds.

Le label « route » est le MODÈLE de route (/v2/booking/reservations/{reservation_id})
et non le chemin réel, sinon chaque code de réservation créerait sa propre
série. Une URL qui ne correspond à aucune route est regroupée sous « unmatched »."""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS


def _route_template(scope: Scope) -> str:
    """Chemin réel → modèle : /v2/booking/reservations/123456 devient
    /v2/booking/reservations/{reservation_id}. FastAPI renseigne
    scope["route"] et scope["path_params"] une fois la route trouvée ; on
    repart du chemin complet car route.path ne contient pas le préfixe
    des routers inclus."""
    if "route" not in scope:
        return "unmatched"
    path = scope["path"]
    for name, value in scope.get("path_params", {}).items():
        path = path.replace(f"/{value}", f"/{{{name}}}", 1)
    return path


class PrometheusMiddleware:
    def __init__(self, app: ASGIApp, excluded_paths: frozenset[str] | set[str] = frozenset()):
        self.app = app
        # Typiquement l'endpoint /metrics : Prometheus l'interroge toutes les
        # 15 s, le compter gonflerait artificiellement le trafic mesuré.
        self.excluded_paths = excluded_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.excluded_paths:
            await self.app(scope, receive, send)
            return

        status_code = 500  # valeur par défaut si une exception remonte sans réponse
        started = time.perf_counter()
        # Fin = dernier morceau de la réponse envoyé au client. Pas la fin de
        # self.app : les tâches de fond (suivi du paiement après
        # POST /reservations) tournent après la réponse et fausseraient la durée.
        duration = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, duration
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                duration = time.perf_counter() - started

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = _route_template(scope)
            HTTP_REQUESTS.labels(
                method=scope["method"],
                route=route,
                status=str(status_code),
                outcome="success" if status_code < 400 else "error",
            ).inc()
            HTTP_REQUEST_DURATION.labels(method=scope["method"], route=route).observe(
                duration if duration is not None else time.perf_counter() - started
            )
