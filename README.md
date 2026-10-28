# Booking — service de réservation

Microservice du projet fil rouge **Parking Management**. Suivi du travail : [JOURNAL.md](JOURNAL.md).

## Rôle

Booking gère la **disponibilité future** du parking et les **réservations** sur des créneaux horaires.
Il répond à la question : « pour ce type de place, entre telle heure et telle heure, reste-t-il une place ? »,
empêche d'accepter plus de réservations que la capacité, puis orchestre le prix (Pricing) et le paiement (Payment).

Booking gère un **nombre de places par type et par heure**, jamais une place précise : l'attribution physique
se fait à l'entrée, côté Access et Parking. Il ne stocke jamais la plaque d'immatriculation, seulement
l'identifiant pseudonymisé fourni par Vehicles.

## Version

**0.4.0**, renvoyée par `GET /health`.

## URL

| | URL |
|---|---|
| API | `<URL Render de booking-api, à compléter>` |
| Swagger | `<URL Render de booking-api>/docs` |
| OpenAPI | `<URL Render de booking-api>/openapi.json` |
| Front | `<URL Render de booking-front, à compléter>` |
| Code | https://github.com/Yanom-school-projects/M1-Projet-Architecture-Booking |

## Fonctionnalités

- [x] Je peux consulter les disponibilités d'un type de place sur un créneau.
- [x] Je peux réserver une place sur un créneau (heures pleines, 30 jours max à l'avance, 7 jours max de durée).
- [x] Je peux empêcher de réserver plus de places que la capacité disponible.
- [x] Je récupère auprès de Parking le nombre de places proposées à la réservation.
- [x] Je peux demander le prix à Pricing.
- [x] Je peux faire payer la réservation avec Payment.
- [x] Je peux obtenir l'identifiant pseudonymisé du véhicule auprès de Vehicles.
- [x] Messages est prévenu quand une réservation est confirmée ou annulée.
- [x] Je peux annuler une réservation confirmée (sans remboursement, extension aux règles métier).
- [x] Access peut vérifier qu'un véhicule possède une réservation valable maintenant.

## Dépendances avec les autres services

| Service | Sens | Échange | Pourquoi ce mode |
|---|---|---|---|
| Vehicles | Booking → Vehicles | `POST /api/vehicles/identify` (`licensePlate`) → `code`, la plaque pseudonymisée, stocké comme `vehicle_id` | HTTP synchrone : l'identifiant est nécessaire pour continuer |
| Pricing | Booking → Pricing | `POST /quote` (zone, `reserved`, durée en minutes) → montant + `quote_id` | HTTP synchrone : le prix est nécessaire avant le paiement |
| Payment | Booking → Payment | `POST /payments` (centimes, clé d'idempotence), puis `GET /payments/{id}` jusqu'à `ACCEPTED`/`REFUSED` | HTTP + interrogation régulière : Payment tranche en 15 à 30 s et ne rappelle pas |
| Parking | Booking → Parking | `GET /parking/availability/{catégorie}/booking` au démarrage puis toutes les heures | HTTP : Parking est l'autorité sur le stock |
| Access | Access → Booking | `GET /reservations/active?vehicle_id=...` → `valid` + type de place réservé | HTTP synchrone : Access doit décider de l'entrée |
| Messages | Booking → bus | événements `booking.confirmed` et `booking.cancelled` (RabbitMQ, exchange `microservice-event-bus`) | Asynchrone : Booking annonce un fait sans attendre |

Correspondance des types de place :

| Booking | Pricing (zone) | Parking (catégorie) |
|---|---|---|
| `standard` | `standard` | `STANDARD` |
| `xl` | `xl` | `XL` |
| `handicap` | `disabled` | `HANDICAPPED` |
| `electrique` | `electric` | `ELECTRIC` |
| `deux_roues` | `two_wheels` | `TWO_WHEELS` |

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | État et version du service |
| GET | `/availability?place_type=&start_at=&end_at=` | Places libres sur un créneau |
| POST | `/reservations` | Créer une réservation (réponse `pending_payment`) |
| GET | `/reservations/{id}` | Suivre une réservation (`pending_payment` → `confirmed` / `failed`) |
| GET | `/reservations/active?vehicle_id=&at=` | Réservation valable à un instant donné, par défaut maintenant (utilisé par Access) |
| GET | `/reservations?vehicle_id=` | Historique des réservations d'un véhicule |
| POST | `/reservations/{id}/cancel` | Annuler une réservation confirmée |
| PUT | `/capacity` | Ajuster la capacité d'un créneau précis |
| POST | `/capacity/sync` | Relancer la synchronisation de capacité avec Parking |

Toutes les dates sont en **UTC**. Une date envoyée avec un fuseau (`2026-11-02T14:00:00+01:00`) est
convertie, une date sans fuseau est lue comme de l'UTC, et les réponses se terminent par `Z`.

Cycle de vie : `pending_payment` → `confirmed` (paiement accepté) ou `failed` (paiement refusé, place libérée) ;
`confirmed` → `cancelled` (annulation, place libérée).

## Tester le service

### En ligne

1. Ouvrir le Swagger (`/docs`).
2. `GET /availability` avec `place_type=standard` et un créneau futur sur des heures pleines, par exemple
   `start_at=2026-11-02T14:00:00Z` et `end_at=2026-11-02T16:00:00Z`.
3. `POST /reservations` :
   ```json
   {
     "vehicle_plate": "AB-123-CD",
     "email": "client@example.com",
     "place_type": "standard",
     "start_at": "2026-11-02T14:00:00Z",
     "end_at": "2026-11-02T16:00:00Z"
   }
   ```
   La réponse a le statut `pending_payment` et un code à 6 chiffres.
4. Après 15 à 30 s, `GET /reservations/{code}` renvoie `confirmed` (ou `failed` si Payment refuse, environ 5 % des cas).

Ou plus simplement avec le front : choisir le type, la date et l'heure (heure de Paris), puis « Réserver ».

À savoir :
- tant que Vehicles n'a pas d'URL, l'étape 3 renvoie **502**, sauf si le mode secours est activé (`VEHICLES_FALLBACK_ENABLED=true`, voir Configuration) ;
- seule la catégorie STANDARD a des places réservables chez Parking pour l'instant ;
- sur le plan gratuit de Render, le premier appel après une période d'inactivité prend environ 30 s.

### En local

```powershell
cd api/V1/booking
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env    # puis compléter les clés

# Mocks Vehicles / Pricing / Payment (facultatif, même contrat que les vrais services)
.\.venv\Scripts\python -m uvicorn mocks.server:app --port 9000

# API
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
```

Front :
```powershell
cd front
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:BOOKING_API_URL = "http://localhost:8000"
.\.venv\Scripts\python -m streamlit run app.py
```

Sans Parking, remplir la capacité à la main : `python scripts/seed_capacity.py --days 3`.

## Configuration

Variables d'environnement, ou fichier `api/V1/booking/.env` (jamais commité) :

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | Base de données (SQLite par défaut) |
| `VEHICLES_SERVICE_URL`, `PRICING_SERVICE_URL`, `PAYMENT_SERVICE_URL`, `PARKING_SERVICE_URL` | URL des services |
| `VEHICLES_API_KEY`, `PRICING_API_KEY`, `PAYMENT_API_KEY`, `PARKING_API_KEY` | Clés envoyées dans l'en-tête `X-API-Key` (vide = pas d'en-tête) |
| `CLOUDAMQP_URL`, `EVENT_BUS_EXCHANGE` | Bus d'événements (vide = événements seulement écrits dans les logs) |
| `PAYMENT_POLL_INTERVAL_SECONDS`, `PAYMENT_POLL_TIMEOUT_SECONDS` | Suivi du paiement (5 s, 180 s) |
| `PARKING_SYNC_INTERVAL_SECONDS` | Synchronisation avec Parking (3600 s) |
| `HTTP_TIMEOUT_SECONDS` | Délai des appels sortants (60 s) |
| `VEHICLES_FALLBACK_ENABLED` | **Temporaire.** `true` : si Vehicles ne répond pas, Booking calcule lui-même l'identifiant du véhicule (empreinte de la plaque, préfixe `tmp-`) au lieu de renvoyer 502. `false` par défaut |
| `VEHICLES_FALLBACK_SECRET` | **Temporaire.** Clé de l'empreinte du mode secours |

## Déploiement (Render)

| | API | Front |
|---|---|---|
| Root Directory | `api/V1/booking` | `front` |
| Build Command | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
| Health Check | `/health` | — |

Chaque push sur `main` redéploie les deux services.

## Architecture

Architecture hexagonale : `domain/` (règles métier pures), `ports/` (interfaces), `application/` (cas d'usage),
`adapters/` (FastAPI, SQLAlchemy, httpx, RabbitMQ). Détails : [docs/booking_architecture.md](docs/booking_architecture.md).

Le problème technique propre au service est la **gestion d'une capacité dans le temps** : une réservation
consomme une place sur chaque heure de son créneau, et une seule heure saturée bloque tout le créneau.
