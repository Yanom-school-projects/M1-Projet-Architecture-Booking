from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/health",
    summary="Vérifier que le service répond",
    response_description="Le service est en ligne.",
)
def health():
    """Endpoint de supervision minimal, sans dépendance à la base de données
    ou aux autres services. Utilisé pour les *health checks* (Render, etc.)."""
    return {"status": "ok"}
