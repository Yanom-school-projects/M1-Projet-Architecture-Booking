"""Middleware ASGI : compte chaque requête HTTP dans http_requests_total.

Le label « route » est le MODÈLE de route (/v2/booking/reservations/{reservation_id})
et non le chemin réel, sinon chaque code de réservation créerait sa propre
série. Une URL qui ne correspond à aucune route est regroupée sous « unmatched »."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.metrics import HTTP_REQUESTS



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

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            HTTP_REQUESTS.labels(
                method=scope["method"],
                route=_route_template(scope),
                status=str(status_code),
                outcome="success" if status_code < 400 else "error",
            ).inc()
