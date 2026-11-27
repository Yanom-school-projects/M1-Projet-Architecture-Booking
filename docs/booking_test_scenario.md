# Scénario de test manuel — service Booking (v2.7.0)

But : dérouler à la main le parcours complet (disponibilité, réservation,
paiement, confirmation, vérification Access, annulation), les cas d'erreur, la
sécurité et l'observabilité. Chaque étape indique le résultat attendu : noter tout
ce qui diverge.

Ce scénario complète les **123 tests automatisés** (`python -m pytest`, voir le
README) : eux vérifient la logique avec de faux services ; ce scénario vérifie
le service réellement lancé, en local ou en ligne.

Toutes les routes sont sous `/v2/booking` et exigent l'en-tête
`X-API-Key: <API_KEY>`, sauf `/health`. Dans Swagger (`/docs`), cliquer
**Authorize** et coller la clé une fois.

---

## 0. Lancement

### En local (mocks)

```powershell
# Terminal 1 : faux Vehicles / Pricing / Payment
cd api/V1/booking
.\.venv\Scripts\python -m uvicorn mocks.server:app --port 9000

# Terminal 2 : API Booking (API_KEY renseignée dans api/V1/booking/.env)
cd api/V1/booking
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload

# Terminal 3 : front
cd front
$env:BOOKING_API_URL = "http://localhost:8000"
$env:BOOKING_API_KEY = "<même valeur que API_KEY>"
.\.venv\Scripts\python -m streamlit run app.py
```

Sans Parking en local, semer une capacité de test (toutes heures, tous types,
`STANDARD=10, XL=3, HANDICAPPED=2, ELECTRIC=3, TWO_WHEELS=5`) :

```powershell
cd api/V1/booking
$env:API_KEY = "<clé>"; .\.venv\Scripts\python scripts\seed_capacity.py --days 3
```

Le script ne touche que `allocated`, jamais les places déjà réservées : on peut le rejouer.

### En ligne

API https://booking-api-vhy5.onrender.com (Swagger : `/docs`), front
https://booking-front-ltvv.onrender.com. La capacité vient de Parking (synchro
toutes les heures). Premier appel après une période d'inactivité : environ 30 s.

✅ `GET /v2/booking/health` renvoie `{"status": "ok", "service": "booking", "version": "2.7.0"}`, sans clé.

---

## A. Parcours nominal via Swagger

1. **`GET /availability`** avec `place_type=STANDARD`, un créneau futur sur des
   quarts d'heure (ex. `start_at=2026-12-02T14:00:00Z`, `end_at=2026-12-02T16:00:00Z`).
   ✅ `available: true`, `min_free_capacity` ≥ 1.

2. **`POST /reservations`** :
   ```json
   {"vehicle_plate": "AB-123-CD", "email": "client@example.com", "place_type": "STANDARD",
    "start_at": "2026-12-02T14:00:00Z", "end_at": "2026-12-02T16:00:00Z"}
   ```
   ✅ 201, statut `pending_payment`, `price_amount` et `payment_id` remplis, `id` à 6 chiffres.
   ✅ En-tête de réponse `X-Correlation-ID` présent. 📝 Noter `id`, `vehicle_id` et cet identifiant.

3. **`GET /reservations/{id}`** tout de suite.
   ✅ Encore `pending_payment` (Payment tranche en quelques secondes avec le mock, 15 à 30 s en ligne).

4. Attendre, puis refaire **`GET /reservations/{id}`**.
   ✅ `confirmed` (ou `failed` si Payment refuse, environ 5 % des cas en ligne).

5. **`GET /availability`** sur le même créneau.
   ✅ `min_free_capacity` a baissé de 1.

6. Logs de l'API.
   ✅ Les lignes de création, de paiement et de confirmation portent toutes le
   même identifiant de corrélation ; l'événement `reservation.confirmed` est publié
   (ou « NON envoyé » sans `CLOUDAMQP_URL`).

---

## B. Parcours nominal via le front

1. Choisir le type, une plaque, un e-mail, puis pour le début et pour la fin une
   **date** et une heure sur les **roulettes** « heures : minutes » (heure de Paris) :
   faire défiler les heures (00 à 23) puis les minutes (00, 15, 30, 45) à la molette,
   au doigt, en maintenant le clic et en tirant vers le haut ou le bas (avec élan), au
   clic sur une valeur ou aux flèches du clavier ; la valeur dans la bande du milieu est
   retenue. ✅ Les roulettes tournent en boucle : après 23 vient 00, après 45 vient 00.
   Par défaut : du prochain quart d'heure à une heure plus tard.
2. Choisir 07 h 45 - 16 h 30 et **Vérifier la disponibilité** : ✅ rappel du créneau
   (« du 28/11/2026 à 07:45 au 28/11/2026 à 16:30 (8 h 45 min) ») et message « Disponible ».
3. Fin avant le début, ou plus de 7 jours : ✅ message clair, aucun appel à Booking.
4. Booking arrêté : ✅ « Booking ne répond pas… », pas de trace d'erreur Python.
5. **Réserver** : ✅ code à 6 chiffres affiché, puis suivi du paiement jusqu'à « confirmée ».
6. Section **Annuler une réservation** avec ce code : ✅ réservation annulée.
7. Code d'annulation mal formé (ex. `12ab`) : ✅ refusé par le front avant tout appel.

📝 Noter l'ergonomie : clarté des messages, temps d'attente, formulaire.

---

## C. Paiement refusé (mock)

Le mock Payment accepte toujours ; une route propre au mock force un refus :
`POST http://localhost:9000/payment/payments/{payment_id}/force-status` avec `{"status": "REFUSED"}`.

1. Créer une réservation (A.2), récupérer `payment_id`.
2. Avant qu'elle soit confirmée, forcer `REFUSED`.
3. **`GET /reservations/{id}`** : ✅ `failed`.
4. **`GET /availability`** : ✅ la place est rendue.
5. Refaire **`GET /reservations/{id}`** : ✅ toujours `failed`, la place n'est pas rendue deux fois.

---

## D. Vérification par Access

Avec la réservation confirmée de A (créneau 14 h – 16 h UTC) :

| Appel `GET /reservations/valid` | Attendu |
|---|---|
| `vehicle_id=<noté>&at=2026-12-02T14:00:00Z` (début) | `valid: true`, type `STANDARD`, sans e-mail |
| `at=2026-12-02T15:30:00Z` (pendant) | `valid: true` |
| `at=2026-12-02T16:00:00Z` (fin) | `valid: false` (fin exclue) |
| `at=2026-12-02T13:59:00Z` (en avance) | `valid: false` (pas de tolérance) |
| `at=2026-12-02T16:30:00+02:00` (fuseau, = 14 h 30 UTC) | `valid: true`, `at` renvoyé en UTC |
| `vehicle_id=inconnu` | 200, `valid: false`, liste vide |
| sans `at` | instant vérifié = maintenant |
| réservation annulée (après G) ou en échec (C) | `valid: false` |

Réservation encore `pending_payment` dont Payment a accepté le paiement : ✅
`valid: true`, et la réservation passe à `confirmed` au passage.

---

## E. Cas d'erreur

| Cas | Comment | Attendu |
|---|---|---|
| Créneau hors quart d'heure | `start_at` à `15:20` | 422 |
| Créneau passé | `start_at` hier | 422 |
| Au-delà de 30 jours | `start_at` dans 31 jours | 422 |
| Durée > 7 jours | `end_at` = `start_at` + 8 jours | 422 |
| `end_at` ≤ `start_at` | `end_at` = `start_at` | 422 |
| Plaque invalide | `"A"`, 21 caractères ou `"AB<script>"` | 422 |
| E-mail invalide | `"pas-un-email"` | 422 |
| Type inconnu | `"place_type": "VIP"` | 422 |
| Plus de place | allouer 1 place (`PUT /capacity-slots`), réserver deux fois | 409 à la 2e |
| Capacité sous le réservé | `PUT /capacity-slots` avec `allocated` < `booked` | 409 |
| Réservation inconnue | `GET /reservations/000000` | 404 |
| Code mal formé | `GET /reservations/abc` | 422 |
| Annuler une réservation non confirmée | `POST /reservations/{id}/cancel` en `pending_payment` | 409 |
| Service dépendant arrêté | couper le mock (Terminal 1), réserver | 502, aucune place consommée |

📝 Vérifier que chaque `detail` est compréhensible.

---

## F. Sécurité

| Appel | Attendu |
|---|---|
| `GET /health` sans clé | 200 |
| `GET /reservations` sans clé | 401, en-tête `WWW-Authenticate: ApiKey` |
| `GET /reservations` avec une mauvaise clé | 401 |
| `GET /reservations` avec la clé | 200 |
| `GET /metrics` avec `Authorization: Bearer <clé>` | 200 |
| `GET /metrics` sans clé | 401 |
| Réponse de n'importe quelle route | en-têtes `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store` |

```powershell
curl.exe -i https://booking-api-vhy5.onrender.com/v2/booking/reservations
curl.exe -i -H "X-API-Key: <clé>" https://booking-api-vhy5.onrender.com/v2/booking/reservations
```

---

## G. Annulation (sans remboursement)

1. Sur une réservation `confirmed` : **`POST /reservations/{id}/cancel`**.
   ✅ 200, statut `cancelled`.
2. **`GET /availability`** : ✅ la place est rendue immédiatement.
3. Annuler une seconde fois : ✅ 409.
4. Logs : ✅ événement `reservation.cancelled` publié, avec l'identifiant de
   corrélation de la **création** de la réservation.

---

## H. Observabilité

1. Envoyer une requête avec `-H "X-Correlation-ID: demo-1234"`.
   ✅ Réponse avec le même en-tête, logs de la requête marqués `demo-1234`.
2. **`GET /metrics`** (avec la clé) : ✅ séries `http_requests_total`,
   `http_request_duration_seconds_bucket` et `parking_operations_total` ; le label
   `route` est le modèle (`/v2/booking/reservations/{reservation_id}`), jamais un code réel.
3. En local, `docker compose up -d --build` puis Grafana (http://localhost:3000) :
   ✅ lignes Disponibilité, Trafic, Opérations métier et Latence remplies après quelques requêtes.
4. Démo de panne : `docker compose stop booking`.
   ✅ Booking passe à `up = 0` dans Grafana ; `docker compose start booking` le rétablit.

---

## I. Quart d'heure

1. Allouer 1 place (`PUT /capacity-slots`) sur chaque quart d'heure de 7 h à 9 h.
2. Réserver 7 h - 7 h 45, puis 7 h 45 - 9 h : ✅ les deux réussissent (aucun quart d'heure en commun).
3. Réserver 7 h 30 - 8 h : ✅ 409, la place est prise sur ces quarts d'heure.
4. `GET /availability` 7 h 45 - 16 h 30 : ✅ accepté ; `08:50` comme début : ✅ 422.

---

## J. Concurrence (optionnel)

1. Allouer 1 seule place sur un créneau.
2. Envoyer deux `POST /reservations` presque simultanés sur ce créneau.
   ✅ Une seule réussit (201), l'autre reçoit 409.

---

## Grille de retours

Pour chaque point : ✅ conforme ou ❌ divergent (comportement observé), remarques
sur les messages ou l'ergonomie, cas non couverts. Les divergences confirmées
deviennent un test automatisé dans `api/V1/booking/tests/`.
