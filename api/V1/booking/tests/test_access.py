"""Vérification d'Access à l'entrée du parking : GET /reservations/valid.

Reprend les 10 cas testés à la main le 28 octobre (voir JOURNAL.md) :
une réservation est valable si elle est `confirmed` et que l'instant vérifié
est dans son créneau, début inclus et fin exclue, sans tolérance."""

from datetime import datetime, timedelta

import pytest

from app.domain.rules import slot_starts
from app.domain.value_objects import PaymentStatus
from tests.fakes import future_slot

PREFIX = "/v2/booking"
URL = f"{PREFIX}/reservations/valid"


@pytest.fixture
def slot(client):
    """Créneau de 10 h à 12 h (UTC) dans deux jours, avec une place."""
    start, end = future_slot(hour=10, hours=2)
    for quarter in slot_starts(start, end):
        client.put(f"{PREFIX}/capacity-slots/STANDARD/{quarter.isoformat()}", json={"allocated": 1})
    return start, end


def reserve(client, start: datetime, end: datetime) -> dict:
    body = {
        "vehicle_plate": "AB-123-CD",
        "email": "client@example.com",
        "place_type": "STANDARD",
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
    }
    response = client.post(f"{PREFIX}/reservations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def check(client, vehicle_id: str, at) -> dict:
    at = at.isoformat() if isinstance(at, datetime) else at
    response = client.get(URL, params={"vehicle_id": vehicle_id, "at": at})
    assert response.status_code == 200  # toujours 200 : `valid` porte la réponse
    return response.json()


@pytest.fixture
def confirmed(client, fakes, slot):
    reservation = reserve(client, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED
    client.get(f"{PREFIX}/reservations/{reservation['id']}")
    return reservation


# 1
def test_debut_du_creneau_inclus(client, confirmed, slot):
    result = check(client, confirmed["vehicle_id"], slot[0])
    assert result["valid"] is True
    assert result["reservations"][0]["id"] == confirmed["id"]


# 2
def test_pendant_le_creneau_avec_le_type_de_place(client, confirmed, slot):
    result = check(client, confirmed["vehicle_id"], slot[0] + timedelta(minutes=75))
    assert result["valid"] is True
    assert result["reservations"][0]["place_type"] == "STANDARD"
    assert "email" not in result["reservations"][0]  # Access n'en a pas besoin


# 3
def test_fin_du_creneau_exclue(client, confirmed, slot):
    assert check(client, confirmed["vehicle_id"], slot[1])["valid"] is False


# 4
def test_arrivee_en_avance_refusee(client, confirmed, slot):
    assert check(client, confirmed["vehicle_id"], slot[0] - timedelta(minutes=1))["valid"] is False


# 5
def test_date_avec_fuseau(client, confirmed, slot):
    # 10 h 30 UTC = 12 h 30 à UTC+2.
    at = (slot[0] + timedelta(hours=2, minutes=30)).isoformat() + "+02:00"
    result = check(client, confirmed["vehicle_id"], at)
    assert result["valid"] is True
    assert result["at"] == (slot[0] + timedelta(minutes=30)).isoformat() + "Z"


# 6
def test_reservation_annulee(client, confirmed, slot):
    client.post(f"{PREFIX}/reservations/{confirmed['id']}/cancel")
    assert check(client, confirmed["vehicle_id"], slot[0])["valid"] is False


# 7
def test_reservation_en_echec(client, fakes, slot):
    reservation = reserve(client, *slot)
    fakes.payment.status = PaymentStatus.REFUSED
    client.get(f"{PREFIX}/reservations/{reservation['id']}")
    assert check(client, reservation["vehicle_id"], slot[0])["valid"] is False


# 8
def test_paiement_accepte_entre_temps(client, fakes, slot):
    # Le suivi en tâche de fond a été coupé : la réservation est encore
    # pending_payment en base, mais Payment l'a acceptée. Le client entre.
    reservation = reserve(client, *slot)
    fakes.payment.status = PaymentStatus.ACCEPTED
    assert check(client, reservation["vehicle_id"], slot[0])["valid"] is True
    assert client.get(f"{PREFIX}/reservations/{reservation['id']}").json()["status"] == "confirmed"


# 9
def test_paiement_toujours_en_attente(client, slot):
    reservation = reserve(client, *slot)
    assert check(client, reservation["vehicle_id"], slot[0])["valid"] is False


# 10
def test_vehicule_inconnu(client, slot):
    result = check(client, "veh-inconnu", slot[0])
    assert result == {"vehicle_id": "veh-inconnu", "at": slot[0].isoformat() + "Z", "valid": False, "reservations": []}


def test_sans_at_verifie_maintenant(client):
    result = client.get(URL, params={"vehicle_id": "veh-inconnu"}).json()
    at = datetime.fromisoformat(result["at"].removesuffix("Z"))
    assert abs(at - datetime.utcnow()) < timedelta(minutes=1)


def test_vehicle_id_obligatoire_et_borne(client):
    assert client.get(URL).status_code == 422
    assert client.get(URL, params={"vehicle_id": "x" * 129}).status_code == 422
