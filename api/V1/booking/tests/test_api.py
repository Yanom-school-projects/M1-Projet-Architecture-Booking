"""Routes HTTP de Booking, de bout en bout dans l'application FastAPI
(validation, codes d'erreur, parcours de réservation, correlation ID,
métriques). Vehicles, Pricing, Payment et le bus sont simulés."""

import re
from datetime import datetime, timedelta

import pytest

from app.domain.enums import PlaceType
from app.domain.value_objects import PaymentStatus
from tests.fakes import booked, current_hour, future_slot

PREFIX = "/v2/booking"


def iso(value: datetime) -> str:
    return value.isoformat()


def put_capacity(client, start: datetime, end: datetime, places: int, place_type: str = "STANDARD") -> None:
    current = start
    while current < end:
        response = client.put(f"{PREFIX}/capacity-slots/{place_type}/{iso(current)}", json={"allocated": places})
        assert response.status_code == 200, response.text
        current += timedelta(hours=1)


def reservation_body(start: datetime, end: datetime, **overrides) -> dict:
    body = {
        "vehicle_plate": "AB-123-CD",
        "email": "client@example.com",
        "place_type": "STANDARD",
        "start_at": iso(start),
        "end_at": iso(end),
    }
    return {**body, **overrides}


@pytest.fixture
def slot(client):
    start, end = future_slot()
    put_capacity(client, start, end, 1)
    return start, end


# --- Capacité et disponibilité ---------------------------------------------


def test_fixer_la_capacite_d_un_creneau(client):
    start, _ = future_slot()
    response = client.put(f"{PREFIX}/capacity-slots/ELECTRIC/{iso(start)}", json={"allocated": 4})
    assert response.status_code == 200
    assert response.json()["allocated"] == 4
    assert response.json()["booked"] == 0
    assert response.json()["slot_start"].endswith("Z")


def test_capacite_negative_refusee(client):
    start, _ = future_slot()
    response = client.put(f"{PREFIX}/capacity-slots/STANDARD/{iso(start)}", json={"allocated": -1})
    assert response.status_code == 422


def test_disponibilite(client, slot):
    start, end = slot
    params = {"place_type": "STANDARD", "start_at": iso(start), "end_at": iso(end)}
    response = client.get(f"{PREFIX}/availability", params=params)
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["min_free_capacity"] == 1


def test_disponibilite_creneau_invalide_422(client):
    start = current_hour() + timedelta(days=2, minutes=30)
    params = {"place_type": "STANDARD", "start_at": iso(start), "end_at": iso(start + timedelta(hours=1))}
    assert client.get(f"{PREFIX}/availability", params=params).status_code == 422


def test_synchro_parking_sans_url_503(client):
    assert client.post(f"{PREFIX}/capacity-slots/sync").status_code == 503


# --- Parcours de réservation --------------------------------------------------


def test_parcours_complet_reservation_paiement_annulation(client, fakes, uow, slot):
    created = client.post(f"{PREFIX}/reservations", json=reservation_body(*slot))
    assert created.status_code == 201, created.text
    reservation = created.json()
    assert reservation["status"] == "pending_payment"
    assert re.fullmatch(r"\d{6}", reservation["id"])
    assert reservation["start_at"].endswith("Z")

    fakes.payment.status = PaymentStatus.ACCEPTED
    confirmed = client.get(f"{PREFIX}/reservations/{reservation['id']}")
    assert confirmed.json()["status"] == "confirmed"

    history = client.get(f"{PREFIX}/reservations", params={"vehicle_id": reservation["vehicle_id"]})
    assert [r["id"] for r in history.json()] == [reservation["id"]]

    cancelled = client.post(f"{PREFIX}/reservations/{reservation['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert booked(uow, PlaceType.STANDARD, *slot) == [0, 0]


def test_creneau_complet_409(client, slot):
    assert client.post(f"{PREFIX}/reservations", json=reservation_body(*slot)).status_code == 201
    response = client.post(f"{PREFIX}/reservations", json=reservation_body(*slot))
    assert response.status_code == 409


def test_creneau_hors_heure_pleine_422(client, slot):
    start, end = slot
    body = reservation_body(start + timedelta(minutes=15), end)
    assert client.post(f"{PREFIX}/reservations", json=body).status_code == 422


def test_date_avec_fuseau_acceptee(client, slot):
    start, end = slot
    # Même créneau exprimé à l'heure de Paris en hiver (UTC+1).
    body = reservation_body(
        start,
        end,
        start_at=(start + timedelta(hours=1)).isoformat() + "+01:00",
        end_at=(end + timedelta(hours=1)).isoformat() + "+01:00",
    )
    response = client.post(f"{PREFIX}/reservations", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["start_at"] == start.isoformat() + "Z"


def test_service_dependant_en_panne_502(client, fakes, slot):
    fakes.pricing.error = RuntimeError("Pricing injoignable")
    assert client.post(f"{PREFIX}/reservations", json=reservation_body(*slot)).status_code == 502


@pytest.mark.parametrize(
    "field, value",
    [
        ("vehicle_plate", "A"),
        ("vehicle_plate", "AB-123-CD-EF-GH-IJ-KLMN"),
        ("vehicle_plate", "AB<script>"),
        ("email", "pas-un-email"),
        ("place_type", "PARKING_VIP"),
    ],
)
def test_entrees_invalides_422(client, slot, field, value):
    response = client.post(f"{PREFIX}/reservations", json=reservation_body(*slot, **{field: value}))
    assert response.status_code == 422


@pytest.mark.parametrize("reservation_id", ["12345", "1234567", "abcdef"])
def test_code_de_reservation_mal_forme_422(client, reservation_id):
    assert client.get(f"{PREFIX}/reservations/{reservation_id}").status_code == 422
    assert client.post(f"{PREFIX}/reservations/{reservation_id}/cancel").status_code == 422


def test_reservation_inconnue_404(client):
    assert client.get(f"{PREFIX}/reservations/000000").status_code == 404
    assert client.post(f"{PREFIX}/reservations/000000/cancel").status_code == 404


def test_annuler_une_reservation_en_attente_409(client, slot):
    reservation = client.post(f"{PREFIX}/reservations", json=reservation_body(*slot)).json()
    assert client.post(f"{PREFIX}/reservations/{reservation['id']}/cancel").status_code == 409


# --- Correlation ID ---------------------------------------------------------


def test_correlation_id_repris_et_renvoye(client):
    response = client.get(f"{PREFIX}/health", headers={"X-Correlation-ID": "front-1234"})
    assert response.headers["X-Correlation-ID"] == "front-1234"


def test_correlation_id_genere_si_absent(client):
    cid = client.get(f"{PREFIX}/health").headers["X-Correlation-ID"]
    assert re.fullmatch(r"[0-9a-f-]{36}", cid)


def test_correlation_id_invalide_remplace(client):
    # Un retour à la ligne pourrait fausser les logs : la valeur est ignorée.
    response = client.get(f"{PREFIX}/health", headers={"X-Correlation-ID": "a b;c"})
    assert response.headers["X-Correlation-ID"] != "a b;c"


def test_correlation_id_conserve_avec_la_reservation(client, uow, slot):
    response = client.post(
        f"{PREFIX}/reservations", json=reservation_body(*slot), headers={"X-Correlation-ID": "parcours-42"}
    )
    assert uow.reservations.get(response.json()["id"]).correlation_id == "parcours-42"


# --- Métriques ----------------------------------------------------------------


def has_series(metrics: str, name: str, **labels: str) -> bool:
    """Une série `name` portant ces labels, quel que soit leur ordre."""
    expected = [f'{key}="{value}"' for key, value in labels.items()]
    return any(
        line.startswith(name + "{") and all(label in line for label in expected) for line in metrics.splitlines()
    )



def test_metriques_comptent_les_requetes_et_les_operations(client, slot):
    client.post(f"{PREFIX}/reservations", json=reservation_body(*slot))
    metrics = client.get(f"{PREFIX}/metrics").text
    assert has_series(
        metrics,
        "http_requests_total",
        method="POST",
        route="/v2/booking/reservations",
        status="201",
        outcome="success",
    )
    assert has_series(
        metrics, "parking_operations_total", service="booking", operation="reservation_create", result="success"
    )
    # Modèle de route, pas le code réel : pas une série par réservation.
    client.get(f"{PREFIX}/reservations/000000")
    metrics = client.get(f"{PREFIX}/metrics").text
    assert 'route="/v2/booking/reservations/{reservation_id}"' in metrics
    assert 'route="/v2/booking/reservations/000000"' not in metrics
