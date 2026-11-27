"""Règles métier pures (domain/rules.py) : aucune base, aucun réseau.
L'heure courante est injectée, les tests ne dépendent donc pas de l'horloge."""

from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.inbound.http.schemas import to_utc_naive
from app.domain.exceptions import InvalidSlotError
from app.domain.rules import hour_slots, validate_slot

NOW = datetime(2026, 12, 1, 9, 25)  # 9 h 25 : l'heure courante est 9 h
HORIZON_DAYS = 30
MAX_HOURS = 24 * 7


def check(start: datetime, end: datetime) -> None:
    validate_slot(start, end, now=NOW, horizon_days=HORIZON_DAYS, max_duration_hours=MAX_HOURS)


def test_creneau_valide():
    check(datetime(2026, 12, 2, 10), datetime(2026, 12, 2, 12))


def test_heure_en_cours_acceptee():
    # Il est 9 h 25 : le créneau de 9 h est encore réservable.
    check(datetime(2026, 12, 1, 9), datetime(2026, 12, 1, 10))


@pytest.mark.parametrize(
    "start, end, message",
    [
        (datetime(2026, 12, 2, 10, 30), datetime(2026, 12, 2, 12), "start_at"),
        (datetime(2026, 12, 2, 10), datetime(2026, 12, 2, 11, 15), "end_at"),
        (datetime(2026, 12, 2, 10, 0, 5), datetime(2026, 12, 2, 12), "start_at"),
    ],
    ids=["debut-pas-pile", "fin-pas-pile", "secondes"],
)
def test_creneau_hors_heure_pleine_refuse(start, end, message):
    with pytest.raises(InvalidSlotError, match=message):
        check(start, end)


@pytest.mark.parametrize("hours", [0, -1], ids=["fin-egale-debut", "fin-avant-debut"])
def test_fin_apres_debut_obligatoire(hours):
    start = datetime(2026, 12, 2, 10)
    with pytest.raises(InvalidSlotError, match="postérieur"):
        check(start, start + timedelta(hours=hours))


def test_creneau_passe_refuse():
    with pytest.raises(InvalidSlotError, match="passé"):
        check(datetime(2026, 12, 1, 8), datetime(2026, 12, 1, 10))


def test_horizon_30_jours():
    limit = datetime(2026, 12, 31, 9)  # heure courante + 30 jours
    check(limit, limit + timedelta(hours=1))
    with pytest.raises(InvalidSlotError, match="horizon"):
        check(limit + timedelta(hours=1), limit + timedelta(hours=2))


def test_duree_maximum_7_jours():
    start = datetime(2026, 12, 2, 10)
    check(start, start + timedelta(hours=MAX_HOURS))
    with pytest.raises(InvalidSlotError, match="Durée"):
        check(start, start + timedelta(hours=MAX_HOURS + 1))


def test_decoupage_en_heures_pleines():
    start = datetime(2026, 12, 2, 22)
    assert hour_slots(start, start + timedelta(hours=3)) == [
        datetime(2026, 12, 2, 22),
        datetime(2026, 12, 2, 23),
        datetime(2026, 12, 3, 0),
    ]
    assert hour_slots(start, start) == []


def test_date_avec_fuseau_convertie_en_utc():
    paris = timezone(timedelta(hours=1))
    assert to_utc_naive(datetime(2026, 12, 2, 14, tzinfo=paris)) == datetime(2026, 12, 2, 13)


def test_date_sans_fuseau_lue_comme_utc():
    assert to_utc_naive(datetime(2026, 12, 2, 14)) == datetime(2026, 12, 2, 14)
