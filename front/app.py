import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import streamlit as st

# Sans le "/" final : sinon les appels partent vers "//reservations" (404).
BOOKING_API_URL = os.environ.get("BOOKING_API_URL", "http://localhost:8000").strip().rstrip("/")
# Large : sur Render, les services en veille mettent ~30 s à se réveiller.
TIMEOUT = 90.0
# Le client saisit l'heure de Paris ; l'API reçoit la date avec son fuseau
# et la convertit elle-même en UTC.
PARIS = ZoneInfo("Europe/Paris")
now_paris = datetime.now(PARIS)

st.set_page_config(page_title="Réservation parking")
st.title("Réserver une place de parking")

PLACE_TYPES = ["standard", "xl", "handicap", "electrique", "deux_roues"]

with st.form("reservation_form"):
    plate = st.text_input("Plaque d'immatriculation", value="AB-123-CD")
    email = st.text_input("Email (pour la confirmation)", value="")
    place_type = st.selectbox("Type de place", PLACE_TYPES)
    date = st.date_input("Date", value=now_paris.date())
    start_hour = st.number_input("Heure de début (heure de Paris)", min_value=0, max_value=23, value=now_paris.hour)
    duration_hours = st.number_input("Durée (heures)", min_value=1, max_value=24 * 7, value=1)
    check_col, submit_col = st.columns(2)
    check = check_col.form_submit_button("Vérifier la disponibilité")
    submit = submit_col.form_submit_button("Réserver")

start_at = datetime.combine(date, datetime.min.time(), tzinfo=PARIS) + timedelta(hours=int(start_hour))
end_at = start_at + timedelta(hours=int(duration_hours))

if check:
    resp = httpx.get(
        f"{BOOKING_API_URL}/availability",
        params={"place_type": place_type, "start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        timeout=TIMEOUT,
    )
    if resp.status_code == 200:
        data = resp.json()
        if data["available"]:
            st.success(f"Disponible ({data['min_free_capacity']} place(s) libre(s) sur le créneau)")
        else:
            st.warning("Aucune place disponible sur ce créneau")
    else:
        st.error(f"Erreur {resp.status_code} : {resp.text}")

if submit:
    resp = httpx.post(
        f"{BOOKING_API_URL}/reservations",
        json={
            "vehicle_plate": plate,
            "email": email,
            "place_type": place_type,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 201:
        st.error(f"Erreur {resp.status_code} : {resp.text}")
    else:
        reservation = resp.json()
        st.session_state["reservation_id"] = reservation["id"]
        st.info(f"Réservation créée — code n° **{reservation['id']}**, en attente de paiement (15 à 30 s)…")

if "reservation_id" in st.session_state:
    reservation_id = st.session_state["reservation_id"]
    resp = httpx.get(f"{BOOKING_API_URL}/reservations/{reservation_id}", timeout=TIMEOUT)
    if resp.status_code == 200:
        reservation = resp.json()
        st.write("Statut de la réservation :", reservation["status"])
        if reservation["status"] == "pending_payment":
            st.button("Rafraîchir le statut")
        elif reservation["status"] == "confirmed":
            st.success(f"Réservation confirmée ! Montant : {reservation['price_amount']} €")
            del st.session_state["reservation_id"]
        elif reservation["status"] == "failed":
            st.error("Le paiement a échoué, réservation annulée")
            del st.session_state["reservation_id"]

st.divider()
st.subheader("Annuler une réservation")
st.caption("Possible uniquement pour une réservation confirmée. La place est libérée, sans remboursement.")

with st.form("cancel_form"):
    cancel_id = st.text_input("Code de réservation (6 chiffres)", max_chars=6)
    cancel_submit = st.form_submit_button("Annuler la réservation")

if cancel_submit:
    resp = httpx.post(f"{BOOKING_API_URL}/reservations/{cancel_id}/cancel", timeout=TIMEOUT)
    if resp.status_code != 200:
        st.error(f"Erreur {resp.status_code} : {resp.text}")
    else:
        st.success(f"Réservation {resp.json()['id']} annulée, la place est libérée.")
