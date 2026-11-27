"""Règles métier pures (domain/rules.py) : aucune base, aucun réseau.
L'heure courante est injectée, les tests ne dépendent donc pas de l'horloge.
Unité de temps : le quart d'heure."""

from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.inbound.http.schemas import to_utc_naive
from app.domain.exceptions import InvalidSlotError
from app.domain.rules import is_slot_aligned, slot_floor, slot_starts, validate_slot

NOW = datetime(2026, 12, 1, 9, 25)  # 9 h 25 : le quart d'heure en cours a commencé à 9 h 15
HORIZON_DAYS = 30
MAX_HOURS = 24 * 7


def check(start: datetime, end: datetime) -> None:
    validate_slot(start, end, now=NOW, horizon_days=HORIZON_DAYS, max_duration_hours=MAX_HOURS)


def test_creneau_au_quart_d_heure_valide():
    check(datetime(2026, 12, 2, 7, 45), datetime(2026, 12, 2, 16, 30))


def test_creneau_d_un_quart_d_heure():
    check(datetime(2026, 12, 2, 10, 15), datetime(2026, 12, 2, 10, 30))


def test_quart_d_heure_en_cours_accepte():
    # Il est 9 h 25 : le quart d'heure de 9 h 15 est encore réservable...
    check(datetime(2026, 12, 1, 9, 15), datetime(2026, 12, 1, 10))
    # ... mais plus celui de 9 h.
    with pytest.raises(InvalidSlotError, match="passé"):
        check(datetime(2026, 12, 1, 9), datetime(2026, 12, 1, 10))


@pytest.mark.parametrize(
    "start, end, message",
    [
        (datetime(2026, 12, 2, 10, 20), datetime(2026, 12, 2, 12), "start_at"),
        (datetime(2026, 12, 2, 10), datetime(2026, 12, 2, 11, 50), "end_at"),
        (datetime(2026, 12, 2, 10, 15, 5), datetime(2026, 12, 2, 12), "start_at"),
    ],
    ids=["debut-hors-quart", "fin-hors-quart", "secondes"],
)
def test_creneau_hors_quart_d_heure_refuse(start, end, message):
    with pytest.raises(InvalidSlotError, match=message):
        check(start, end)


@pytest.mark.parametrize("minutes", [0, -15], ids=["fin-egale-debut", "fin-avant-debut"])
def test_fin_apres_debut_obligatoire(minutes):
    start = datetime(2026, 12, 2, 10)
    with pytest.raises(InvalidSlotError, match="postérieur"):
        check(start, start + timedelta(minutes=minutes))


def test_creneau_passe_refuse():
    with pytest.raises(InvalidSlotError, match="passé"):
        check(datetime(2026, 12, 1, 8), datetime(2026, 12, 1, 10))


def test_horizon_30_jours():
    limit = datetime(2026, 12, 31, 9, 15)  # quart d'heure en cours + 30 jours
    check(limit, limit + timedelta(minutes=15))
    with pytest.raises(InvalidSlotError, match="horizon"):
        check(limit + timedelta(minutes=15), limit + timedelta(minutes=30))


def test_duree_maximum_7_jours():
    start = datetime(2026, 12, 2, 10)
    check(start, start + timedelta(hours=MAX_HOURS))
    with pytest.raises(InvalidSlotError, match="Durée"):
        check(start, start + timedelta(hours=MAX_HOURS, minutes=15))


def test_decoupage_en_quarts_d_heure():
    start = datetime(2026, 12, 2, 23, 30)
    assert slot_starts(start, start + timedelta(hours=1)) == [
        datetime(2026, 12, 2, 23, 30),
        datetime(2026, 12, 2, 23, 45),
        datetime(2026, 12, 3, 0, 0),
        datetime(2026, 12, 3, 0, 15),
    ]
    assert slot_starts(start, start) == []
    assert len(slot_starts(datetime(2026, 12, 2, 7, 45), datetime(2026, 12, 2, 16, 30))) == 35


def test_alignement_et_debut_du_quart_d_heure():
    assert is_slot_aligned(datetime(2026, 12, 2, 7, 45))
    assert not is_slot_aligned(datetime(2026, 12, 2, 7, 50))
    assert slot_floor(datetime(2026, 12, 2, 7, 59, 59)) == datetime(2026, 12, 2, 7, 45)


def test_date_avec_fuseau_convertie_en_utc():
    paris = timezone(timedelta(hours=1))
    assert to_utc_naive(datetime(2026, 12, 2, 14, tzinfo=paris)) == datetime(2026, 12, 2, 13)


def test_date_sans_fuseau_lue_comme_utc():
    assert to_utc_naive(datetime(2026, 12, 2, 14)) == datetime(2026, 12, 2, 14)
