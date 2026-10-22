from fastapi import APIRouter, Request

router = APIRouter()


@router.get(
    "/health",
    summary="Vérifier que le service répond",
    response_description="Le service est en ligne.",
)
def health(request: Request):
    """Endpoint de supervision minimal, sans dépendance à la base de données
    ou aux autres services. Utilisé pour les *health checks* (Render, etc.).
    Indique la version déployée."""
    return {"status": "ok", "service": "booking", "version": request.app.version}
