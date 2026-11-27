"""Sécurité (jalon 15) : clé d'API unique sur les routes métier et /metrics,
/health public, erreurs 500 sans détail interne, en-têtes HTTP."""

import pytest

from app.config import settings
from tests.conftest import API_KEY

PREFIX = "/v2/booking"

PROTECTED_ROUTES = [
    ("GET", f"{PREFIX}/availability?place_type=STANDARD&start_at=2030-01-01T10:00:00&end_at=2030-01-01T11:00:00"),
    ("POST", f"{PREFIX}/reservations"),
    ("GET", f"{PREFIX}/reservations"),
    ("GET", f"{PREFIX}/reservations/123456"),
    ("POST", f"{PREFIX}/reservations/123456/cancel"),
    ("GET", f"{PREFIX}/reservations/valid?vehicle_id=veh-1"),
    ("PUT", f"{PREFIX}/capacity-slots/STANDARD/2030-01-01T10:00:00"),
    ("POST", f"{PREFIX}/capacity-slots/sync"),
    ("GET", f"{PREFIX}/metrics"),
]


def test_health_public_avec_version(anonymous):
    response = anonymous.get(f"{PREFIX}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "booking", "version": "2.5.0"}


@pytest.mark.parametrize("method, url", PROTECTED_ROUTES)
def test_sans_cle_401(anonymous, method, url):
    response = anonymous.request(method, url)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "ApiKey"


@pytest.mark.parametrize("method, url", PROTECTED_ROUTES)
def test_mauvaise_cle_401(anonymous, method, url):
    response = anonymous.request(method, url, headers={"X-API-Key": "mauvaise-cle"})
    assert response.status_code == 401


@pytest.mark.parametrize("method, url", PROTECTED_ROUTES)
def test_bonne_cle_passe_la_securite(client, method, url):
    # Le corps manque pour certaines routes (422) ou Parking n'est pas
    # configuré (503) : l'important est d'avoir franchi le contrôle d'accès.
    assert client.request(method, url).status_code not in (401, 403)


def test_cle_non_ascii_refusee_sans_planter(anonymous):
    response = anonymous.get(f"{PREFIX}/reservations", headers={"X-API-Key": "clé-é".encode()})
    assert response.status_code == 401


def test_sans_cle_configuree_tout_est_refuse(client, monkeypatch):
    # Échec fermé : une clé oubliée dans Render ne doit pas ouvrir l'API.
    monkeypatch.setattr(settings, "api_key", "")
    assert client.get(f"{PREFIX}/reservations").status_code == 401
    assert client.get(f"{PREFIX}/health").status_code == 200


def test_metrics_avec_la_cle(client):
    response = client.get(f"{PREFIX}/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "parking_operations_total" in response.text


def test_metrics_en_bearer_pour_prometheus(anonymous):
    response = anonymous.get(f"{PREFIX}/metrics", headers={"Authorization": f"Bearer {API_KEY}"})
    assert response.status_code == 200
    wrong = anonymous.get(f"{PREFIX}/metrics", headers={"Authorization": "Bearer mauvaise-cle"})
    assert wrong.status_code == 401


def test_bearer_refuse_sur_les_routes_metier(anonymous):
    response = anonymous.get(f"{PREFIX}/reservations", headers={"Authorization": f"Bearer {API_KEY}"})
    assert response.status_code == 401


def test_swagger_declare_la_cle(anonymous):
    schema = anonymous.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    assert "security" not in schema["paths"][f"{PREFIX}/health"]["get"]
    assert "security" in schema["paths"][f"{PREFIX}/reservations"]["post"]


def test_erreur_500_generique_avec_correlation_id(client, app):
    from app.adapters.inbound.http.dependencies import get_reservation_service

    def broken():
        raise RuntimeError("SELECT * FROM reservations -- détail interne")

    app.dependency_overrides[get_reservation_service] = broken
    response = client.get(f"{PREFIX}/reservations", headers={"X-Correlation-ID": "test-500"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Erreur interne du service Booking", "correlation_id": "test-500"}
    assert "SELECT" not in response.text


def test_entetes_de_securite(client):
    response = client.get(f"{PREFIX}/reservations")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
