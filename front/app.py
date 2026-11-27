import os
import time
from datetime import datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

import httpx
import streamlit as st
from time_picker import time_wheel

# Sans le "/" final : sinon les appels partent vers "//reservations" (404).
BOOKING_API_URL = os.environ.get("BOOKING_API_URL", "http://localhost:8000").strip().rstrip("/")
# Clé d'API de Booking (même valeur que son API_KEY). Le front est
# rendu côté serveur par Streamlit : la clé ne part jamais dans le navigateur.
BOOKING_API_KEY = os.environ.get("BOOKING_API_KEY", "").strip()
HEADERS = {"X-API-Key": BOOKING_API_KEY} if BOOKING_API_KEY else {}
# Large : sur Render gratuit, Booking puis Pricing et Payment peuvent
# chacun mettre 30 à 60 s à se réveiller.
TIMEOUT = 180.0
# Suivi automatique du paiement : toutes les 3 s, pendant 5 min au plus.
POLL_SECONDS = 3
POLL_MAX_SECONDS = 300
# Le client saisit l'heure de Paris ; l'API reçoit la date avec son fuseau
# et la convertit elle-même en UTC.
PARIS = ZoneInfo("Europe/Paris")
now_paris = datetime.now(PARIS)

st.set_page_config(page_title="Réservation parking")
st.title("Réserver une place de parking")

# Code envoyé à Booking -> libellé affiché au client.
PLACE_TYPES = {
    "STANDARD": "Standard",
    "HANDICAPPED": "PMR",
    "ELECTRIC": "Électrique",
    "XL": "XL",
    "TWO_WHEELS": "Deux-roues",
}

# Mêmes règles que Booking, vérifiées ici pour afficher un message clair avant
# tout appel : créneaux au quart d'heure, 30 jours à l'avance, 7 jours au plus.
HORIZON_DAYS = 30
MAX_DURATION = timedelta(days=7)
SLOT_MINUTES = 15
DATE_FORMAT = "DD/MM/YYYY"


def pick_moment(column, label: str, default: datetime, max_day) -> datetime:
    """Une date, puis l'heure sur les roulettes heures : minutes (voir time_picker.py)."""
    with column:
        day = st.date_input(
            f"{label} : date", value=default.date(), min_value=today, max_value=max_day, format=DATE_FORMAT
        )
        at = time_wheel(f"{label} : heure", default.time(), key=f"heure-{label}")
    return paris_datetime(day, at)


def slot_floor(value: datetime) -> datetime:
    """Début du quart d'heure qui contient `value` (9 h 25 -> 9 h 15)."""
    return value.replace(minute=value.minute - value.minute % SLOT_MINUTES, second=0, microsecond=0)


def paris_datetime(day, at: dtime) -> datetime:
    return datetime.combine(day, at, tzinfo=PARIS)


def slot_error(start: datetime, end: datetime) -> str | None:
    """Message à afficher si le créneau ne respecte pas les règles, sinon None."""
    current_slot = slot_floor(datetime.now(PARIS))
    if end <= start:
        return "La fin doit être après le début."
    if start < current_slot:
        return "Le début du créneau est déjà passé."
    if start > current_slot + timedelta(days=HORIZON_DAYS):
        return f"On ne peut pas réserver plus de {HORIZON_DAYS} jours à l'avance."
    if end - start > MAX_DURATION:
        return "Une réservation dure 7 jours au plus."
    return None


def describe_slot(start: datetime, end: datetime) -> str:
    minutes = int((end - start).total_seconds() // 60)
    days, rest = divmod(minutes, 24 * 60)
    hours, minutes = divmod(rest, 60)
    parts = (f"{days} j" if days else "", f"{hours} h" if hours else "", f"{minutes} min" if minutes else "")
    duration = " ".join(part for part in parts if part)
    return f"du {start:%d/%m/%Y à %H:%M} au {end:%d/%m/%Y à %H:%M} ({duration})"


# Par défaut : du prochain quart d'heure à une heure plus tard.
default_start = slot_floor(now_paris) + timedelta(minutes=SLOT_MINUTES)
default_end = default_start + timedelta(hours=1)
today = now_paris.date()

with st.form("reservation_form"):
    plate = st.text_input("Plaque d'immatriculation", value="AB-123-CD")
    email = st.text_input("Email (pour la confirmation)", value="")
    place_type = st.selectbox("Type de place", list(PLACE_TYPES), format_func=PLACE_TYPES.get)

    start_col, end_col = st.columns(2)
    start_at = pick_moment(start_col, "Début", default_start, today + timedelta(days=HORIZON_DAYS))
    end_at = pick_moment(end_col, "Fin", default_end, today + timedelta(days=HORIZON_DAYS) + MAX_DURATION)

    check_col, submit_col = st.columns(2)
    check = check_col.form_submit_button("Vérifier la disponibilité")
    submit = submit_col.form_submit_button("Réserver")

if check or submit:
    error = slot_error(start_at, end_at)
    if error:
        st.error(error)
        check = submit = False
    else:
        st.caption(f"Créneau {describe_slot(start_at, end_at)}")

UNREACHABLE = "Booking ne répond pas (service en veille ou injoignable). Réessayez dans une minute."

if check:
    try:
        resp = httpx.get(
            f"{BOOKING_API_URL}/v2/booking/availability",
            params={"place_type": place_type, "start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        resp = None
        st.error(UNREACHABLE)
    if resp is None:
        pass
    elif resp.status_code == 200:
        data = resp.json()
        if data["available"]:
            st.success(f"Disponible ({data['min_free_capacity']} place(s) libre(s) sur le créneau)")
        else:
            st.warning("Aucune place disponible sur ce créneau")
    else:
        st.error(f"Erreur {resp.status_code} : {resp.text}")

if submit:
    try:
        with st.spinner("Réservation en cours (jusqu'à 1 à 2 min si les services sont en veille)…"):
            resp = httpx.post(
                f"{BOOKING_API_URL}/v2/booking/reservations",
                json={
                    "vehicle_plate": plate,
                    "email": email,
                    "place_type": place_type,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                },
                headers=HEADERS,
                timeout=TIMEOUT,
            )
    except httpx.HTTPError:
        resp = None
        st.error(UNREACHABLE)
    if resp is None:
        pass
    elif resp.status_code != 201:
        st.error(f"Erreur {resp.status_code} : {resp.text}")
    else:
        reservation = resp.json()
        st.session_state["reservation_id"] = reservation["id"]
        st.session_state["followed_since"] = time.monotonic()


@st.fragment(run_every=POLL_SECONDS)
def follow_payment():
    """Relancé seul toutes les POLL_SECONDS secondes tant que le paiement est
    en attente. Au statut final, relance toute la page : le fragment n'est
    plus affiché et l'actualisation s'arrête."""
    reservation_id = st.session_state["reservation_id"]
    if time.monotonic() - st.session_state["followed_since"] > POLL_MAX_SECONDS:
        del st.session_state["reservation_id"]
        st.session_state["result"] = ("pending", reservation_id, None)
        st.rerun()
    try:
        resp = httpx.get(f"{BOOKING_API_URL}/v2/booking/reservations/{reservation_id}", headers=HEADERS, timeout=30)
    except httpx.HTTPError:
        st.info(f"Réservation n° **{reservation_id}** : statut momentanément indisponible, nouvel essai…")
        return
    if resp.status_code != 200:
        st.error(f"Erreur {resp.status_code} : {resp.text}")
        return
    reservation = resp.json()
    if reservation["status"] == "pending_payment":
        st.info(f"Réservation n° **{reservation_id}** créée : paiement en cours de validation…")
        return
    del st.session_state["reservation_id"]
    st.session_state["result"] = (reservation["status"], reservation_id, reservation)
    st.rerun()


if "reservation_id" in st.session_state:
    follow_payment()

if "result" in st.session_state:
    status, reservation_id, reservation = st.session_state.pop("result")
    if status == "confirmed":
        label = PLACE_TYPES.get(reservation["place_type"], reservation["place_type"])
        st.success(
            f"Réservation n° **{reservation_id}** confirmée ! Place {label}, montant : {reservation['price_amount']} €"
        )
    elif status == "failed":
        st.error(f"Réservation n° **{reservation_id}** : le paiement a été refusé, réservation annulée.")
    elif status == "pending":
        st.warning(
            f"Réservation n° **{reservation_id}** : paiement toujours en attente. "
            "Gardez ce code, le statut sera mis à jour par Booking."
        )
    else:
        st.write(f"Réservation n° **{reservation_id}** : statut {status}")

st.divider()
st.subheader("Annuler une réservation")
st.caption("Possible uniquement pour une réservation confirmée. La place est libérée, sans remboursement.")

with st.form("cancel_form"):
    cancel_id = st.text_input("Code de réservation (6 chiffres)", max_chars=6)
    cancel_submit = st.form_submit_button("Annuler la réservation")

if cancel_submit and not (cancel_id.isdigit() and len(cancel_id) == 6):
    # Vérifié avant de construire l'URL : le code saisi y est inséré tel quel.
    st.error("Le code de réservation comporte 6 chiffres.")
elif cancel_submit:
    try:
        resp = httpx.post(
            f"{BOOKING_API_URL}/v2/booking/reservations/{cancel_id}/cancel", headers=HEADERS, timeout=TIMEOUT
        )
    except httpx.HTTPError:
        resp = None
        st.error(UNREACHABLE)
    if resp is None:
        pass
    elif resp.status_code != 200:
        st.error(f"Erreur {resp.status_code} : {resp.text}")
    else:
        st.success(f"Réservation {resp.json()['id']} annulée, la place est libérée.")
