# Scénario de test — service Booking (MVP)

But : dérouler le flux complet (dispo → réservation → paiement async → confirmation → annulation) et les cas limites, pour remonter des retours. Chaque étape indique le résultat attendu — note tout ce qui diverge.

⚠️ Pas de migrations en place (pas d'Alembic pour ce MVP) : si une erreur type `no such column` apparaît après avoir récupéré une mise à jour du code, c'est que le schéma a changé — supprime `api/V1/booking/booking.db` (perte des données de test locales, sans conséquence) et relance l'API pour qu'elle recrée la base à jour.

## 0. Lancement (3 terminaux)

```powershell
# Terminal 1 — mocks Vehicles/Pricing/Payment
cd "api/V1/booking"
.\.venv\Scripts\python.exe -m uvicorn mocks.server:app --port 9000 --reload

# Terminal 2 — API Booking
cd "api/V1/booking"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload

# Terminal 3 — front Streamlit
cd "front"
$env:BOOKING_API_URL = "http://localhost:8000"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Ouvrir :
- Swagger Booking : http://localhost:8000/docs
- Swagger mocks : http://localhost:9000/docs
- Front : http://localhost:8501

### Semer une capacité de base

La base démarre vide : tant que personne n'a appelé `PUT /capacity` sur un
créneau, il est normal d'obtenir `409 Aucune capacité disponible`. En
attendant que le service Parking existe, un script sème une capacité de
référence sur les prochains jours, toutes heures et tous types de place :

```powershell
# Terminal 4 (ou dans Terminal 2 une fois l'API lancée)
cd "api/V1/booking"
.\.venv\Scripts\python.exe scripts\seed_capacity.py --days 3
```

Répartition par défaut : `standard=10, xl=3, handicap=2, electrique=3, deux_roues=5`,
modifiable dans `scripts/seed_capacity.py`. Rejouable sans risque : il ne
touche que `allocated`, jamais les places déjà réservées (`booked`). Les
scénarios C, D et F ci-dessous ont volontairement besoin d'une capacité
précise (souvent 1 place) : ils repassent par `PUT /capacity` en ciblé plutôt
que par ce script.

✅ Attendu : les 3 pages se chargent, `GET /health` sur Booking renvoie `{"status": "ok"}`.

---

## A. Happy path via Swagger

1. **`PUT /capacity`** : alloue de la capacité pour tester, ex. `place_type=standard`, `slot_start` = une heure pleine future (aujourd'hui + quelques heures, format `2026-09-02T18:00:00`), `allocated=2`. Refaire pour l'heure suivante si le créneau testé dure 2h.
   ✅ Réponse 200 avec les valeurs envoyées.

2. **`GET /availability`** avec le même `place_type`/`start_at`/`end_at`.
   ✅ `available: true`, `min_free_capacity` = valeur allouée.

3. **`POST /reservations`** avec une plaque au choix, même type/créneau.
   ✅ 201, statut `pending_payment`, `price_amount` rempli, `payment_id` rempli.
   📝 Note l'`id` de la réservation renvoyée.

4. **`GET /reservations/{id}`** immédiatement.
   ✅ Statut encore `pending_payment` (le mock Payment répond après ~3s).

5. Attendre 3–5s, refaire **`GET /reservations/{id}`**.
   ✅ Statut passé à `confirmed`.

6. Refaire **`GET /availability`** sur le même créneau.
   ✅ `min_free_capacity` a diminué de 1.

7. Regarder le terminal de l'API Booking (Terminal 2).
   ✅ Une ligne de log `event published type=reservation.confirmed payload=...` doit apparaître (c'est l'événement que Messages consommera plus tard).

---

## B. Happy path via le front

1. Sur http://localhost:8501, remplir le formulaire avec un créneau **déjà alloué** (via A.1, ou en refaire un nouveau via Swagger `PUT /capacity`).
2. Cliquer **Vérifier la disponibilité**.
   ✅ Message vert "Disponible (...)".
3. Cliquer **Réserver**.
   ✅ Message bleu "Réservation créée (...), en attente de paiement…", puis le statut affiché est `pending_payment`.
4. Cliquer **Rafraîchir le statut** après quelques secondes.
   ✅ Finit par afficher "Réservation confirmée ! Montant : X €".

📝 Note l'ergonomie : est-ce clair, faut-il cliquer plusieurs fois, le formulaire est-il pratique (heure/durée) ?

---

## C. Paiement refusé (impossible à obtenir "naturellement" — le mock ne fait que payer)

Le mock expose une route de test dédiée pour forcer un statut sans attendre les 3s automatiques :
`POST http://localhost:9000/payment/payments/{payment_id}/force-status` avec `{"status": "refused"}` (ou `"cancelled"`).

1. Crée une réservation (comme en A.3), récupère `payment_id`.
2. **Avant 3 secondes**, appelle `force-status` avec `status=refused` (sur le Swagger des mocks, port 9000).
3. **`GET /reservations/{id}`** côté Booking.
   ✅ Statut `failed`.
4. **`GET /availability`** sur le créneau concerné.
   ✅ La capacité reprise a été **libérée** (remontée par rapport à juste après la réservation).
5. Attendre que les 3s originales soient passées (au cas où l'auto-confirmation du mock tenterait de repasser en `paid`).
   ✅ Le statut reste `failed` (pas d'écrasement) — c'est le test de l'idempotence du webhook.

---

## D. Cas d'erreur attendus

À tester via Swagger (`POST /reservations`), chacun doit renvoyer le code indiqué :

| Cas | Comment le provoquer | Code attendu |
|---|---|---|
| Créneau non aligné sur une heure pleine | `start_at` avec des minutes ≠ 00, ex. `...T15:30:00` | 422 |
| Créneau déjà passé | `start_at` dans le passé | 422 |
| Créneau à plus de 30 jours | `start_at` = aujourd'hui + 31 jours | 422 |
| Durée > 7 jours | `end_at` = `start_at` + 8 jours | 422 |
| `end_at` avant/égal `start_at` | `end_at` = `start_at` | 422 |
| Aucune capacité allouée sur le créneau | Un créneau/type jamais passé par `PUT /capacity` | 409 |
| Capacité épuisée | Allouer 1 place, réserver deux fois de suite le même créneau | 409 sur la 2e réservation |
| Réservation inconnue (bon format, n'existe pas) | `GET /reservations/999999` | 404 |
| Code de réservation mal formé | `GET /reservations/abc` | 422 |

📝 Vérifie aussi que le message d'erreur (`detail`) est compréhensible.

---

## E. Vérification manuelle du webhook (bonus, avec Swagger des mocks ou curl)

Rejouer **deux fois** le même appel `POST /webhooks/payment` (même `payment_id`/`reference`/`status=paid`) sur une réservation déjà `confirmed`.
✅ Le deuxième appel ne doit rien casser (toujours `{"received": true}`) et ne doit pas republier l'événement une deuxième fois (vérifier les logs de l'API).

---

## F. Concurrence légère (optionnel)

1. Alloue 1 seule place pour un créneau.
2. Ouvre deux onglets Swagger (ou deux requêtes rapprochées) et envoie 2× `POST /reservations` sur ce créneau presque simultanément.
   ✅ Une seule doit réussir (201), l'autre doit recevoir 409.

---

## G. Annulation avec remboursement de 50%

Nouveauté : une réservation **confirmée** peut être annulée par le client
(`POST /reservations/{id}/cancel`). Le client est remboursé de la moitié du
montant payé, l'autre moitié reste acquise au parking. Convention testée via
le mock : Booking rappelle Payment avec la même référence (l'id de
réservation) et un montant à moitié prix ; Payment détecte l'écart avec ce
qu'il avait déjà encaissé et déclenche un remboursement de la différence — **à
confirmer avec qui implémente réellement Payment**, ce n'est qu'une
hypothèse de contrat pour l'instant.

1. Crée une réservation et force son paiement (`force-status` avec `status=paid`, ou attends les 3s automatiques).
2. **`POST /reservations/{id}/cancel`**.
   ✅ 201/200, statut `cancellation_pending`, `refund_amount` = moitié de `price_amount` (ex. 2.00 € payé → 1.00 € de `refund_amount`).
3. **`GET /availability`** sur le créneau, immédiatement.
   ✅ La capacité est déjà libérée (pas besoin d'attendre la confirmation du remboursement).
4. Réessaie **`POST /reservations/{id}/cancel`** sur la même réservation.
   ✅ 409 (déjà en cours d'annulation).
5. Attends ~2-3s (le mock confirme le remboursement plus vite qu'un paiement), puis **`GET /reservations/{id}`**.
   ✅ Statut `cancelled`, `refund_amount` inchangé.
6. Vérifie dans les logs de l'API Booking la ligne `event published type=reservation.cancelled`.
7. Essaie d'annuler une réservation qui n'est **pas** `confirmed` (ex. encore `pending_payment`, ou déjà `cancelled`).
   ✅ 409 avec un message indiquant le statut actuel.

Testable aussi via le front : section "Annuler une réservation" en bas de page, en collant le code à 6 chiffres reçu à la création.

---

## Grille de retours

Pour chaque point testé, note :
- ✅ conforme / ❌ divergent (avec le comportement observé)
- Remarques UX/API (messages peu clairs, champ manquant, ordre des questions du front, etc.)
- Idées de cas non couverts par ce scénario

Renvoie-moi cette liste (même brute) et on ajuste le code en conséquence.
