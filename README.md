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

**2.6.0**, renvoyée par `GET /v2/booking/health`. Définie à un seul endroit (`app/__init__.py`) et marquée
par un tag Git `v2.6.0` ; la CI vérifie que le tag et le code concordent.

| Version | Contenu |
|---|---|
| 2.6.0 | Durée des requêtes (`http_request_duration_seconds`) et latence dans Grafana, mode secours Vehicles retiré |
| 2.5.0 | Sécurité : clé d'API, entrées validées, erreurs 500 sans détail ; tests pytest et CI GitHub Actions |

Dernière mise à jour : **27 novembre**.

## URL

| | URL |
|---|---|
| API | https://booking-api-vhy5.onrender.com |
| Swagger | https://booking-api-vhy5.onrender.com/docs |
| OpenAPI | https://booking-api-vhy5.onrender.com/openapi.json |
| Métriques | https://booking-api-vhy5.onrender.com/v2/booking/metrics |
| Front | https://booking-front-ltvv.onrender.com |
| Code | https://github.com/Yanom-school-projects/M1-Projet-Architecture-Booking |

## État de maturité

0 = non commencé, 1 = en cours, 2 = fonctionnel, 3 = maîtrisé

| Aspect | État | Constat |
|---|---|---|
| Métier | 3 | Capacité par type et par heure, créneaux, cycle de vie, idempotence du paiement. Écart assumé : annulation sans remboursement. |
| API / Déploiement | 2 | Sur Render, routes sous `/v2/booking`, `/health` avec version, Swagger. Base Postgres en ligne : les réservations survivent aux mises en veille et redéploiements. |
| Intégration | 2 | Vehicles, Pricing, Payment, Parking, RabbitMQ (Messages) réels ; Access interroge `/reservations/valid`. Correlation ID propagé à tous les appels. |
| Interface | 2 | Front Streamlit (heure de Paris) + tableau de bord Grafana. |
| Qualité | 2 | Logs fichier/console avec correlation ID, erreurs propres, `/metrics` Prometheus (trafic, durée, métier), 112 tests pytest (métier, API, Access, sécurité). |
| CI/CD | 2 | GitHub Actions à chaque push : lint, tests, bandit, pip-audit, gitleaks, build et démarrage des images. Déploiement automatique Render. |
| Sécurité | 2 | Clé d'API sur toutes les routes métier et `/metrics`, entrées validées, erreurs sans détail interne, secrets hors de Git, conteneurs non-root. |

Reste à faire avant le rendu : [todolist.md](todolist.md).

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
| Vehicles | Booking → Vehicles | `POST /api/vehicle/create` (`licensePlate`) → `code`, la plaque pseudonymisée, stocké comme `vehicle_id` | HTTP synchrone : l'identifiant est nécessaire pour continuer |
| Pricing | Booking → Pricing | `POST /quote` (zone, `reserved`, durée en minutes) → montant + `quote_id` | HTTP synchrone : le prix est nécessaire avant le paiement |
| Payment | Booking → Payment | `POST /payments` (centimes, clé d'idempotence), puis `GET /payments/{id}` jusqu'à `ACCEPTED`/`REFUSED` | HTTP + interrogation régulière : Payment tranche en 15 à 30 s et ne rappelle pas |
| Parking | Booking → Parking | `GET /parking/availability/{catégorie}/booking` au démarrage puis toutes les heures | HTTP : Parking est l'autorité sur le stock |
| Access | Access → Booking | `GET /v2/booking/reservations/valid?vehicle_id=...` → `valid` + type de place réservé | HTTP synchrone : Access doit décider de l'entrée |
| Messages | Booking → bus | événements `booking.confirmed` et `booking.cancelled` (RabbitMQ, exchange `microservice-event-bus`) | Asynchrone : Booking annonce un fait sans attendre |

Correspondance des types de place :

Nomenclature commune à tous les microservices : le code est la seule valeur échangée (API, Parking, Pricing,
événements), sans correspondance propre à un service. Le libellé est affiché dans le front et envoyé à
Notification (champ `place_type_label` des événements, à côté du code `place_type`).

| Code | Libellé affiché |
|---|---|
| `STANDARD` | Standard |
| `HANDICAPPED` | PMR |
| `ELECTRIC` | Électrique |
| `XL` | XL |
| `TWO_WHEELS` | Deux-roues |

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/v2/booking/health` | État et version du service |
| GET | `/v2/booking/availability?place_type=&start_at=&end_at=` | Places libres sur un créneau |
| POST | `/v2/booking/reservations` | Créer une réservation (réponse `pending_payment`) |
| GET | `/v2/booking/reservations/{id}` | Suivre une réservation (`pending_payment` → `confirmed` / `failed`) |
| GET | `/v2/booking/reservations/valid?vehicle_id=&at=` | Réservation valable à un instant donné, par défaut maintenant (utilisé par Access) |
| GET | `/v2/booking/reservations?vehicle_id=` | Historique des réservations d'un véhicule |
| POST | `/v2/booking/reservations/{id}/cancel` | Annuler une réservation confirmée |
| PUT | `/v2/booking/capacity-slots/{place_type}/{slot_start}` | Ajuster la capacité d'un créneau précis |
| POST | `/v2/booking/capacity-slots/sync` | Relancer la synchronisation de capacité avec Parking |
| GET | `/v2/booking/metrics` | Métriques au format Prometheus (hors Swagger) |

Toutes ces routes, sauf `/health`, exigent la clé d'API : voir [Sécurité](#sécurité).

Toutes les dates sont en **UTC**. Une date envoyée avec un fuseau (`2026-11-02T14:00:00+01:00`) est
convertie, une date sans fuseau est lue comme de l'UTC, et les réponses se terminent par `Z`.

Cycle de vie : `pending_payment` → `confirmed` (paiement accepté) ou `failed` (paiement refusé, place libérée) ;
`confirmed` → `cancelled` (annulation, place libérée).

## Tester le service

### En ligne

1. Ouvrir le Swagger (`/docs`), cliquer sur **Authorize** et coller la clé d'API.
2. `GET /v2/booking/availability` avec `place_type=STANDARD` et un créneau futur sur des heures pleines, par exemple
   `start_at=2026-11-02T14:00:00Z` et `end_at=2026-11-02T16:00:00Z`.
3. `POST /v2/booking/reservations` :
   ```json
   {
     "vehicle_plate": "AB-123-CD",
     "email": "client@example.com",
     "place_type": "STANDARD",
     "start_at": "2026-11-02T14:00:00Z",
     "end_at": "2026-11-02T16:00:00Z"
   }
   ```
   La réponse a le statut `pending_payment` et un code à 6 chiffres.
4. Après 15 à 30 s, `GET /v2/booking/reservations/{code}` renvoie `confirmed` (ou `failed` si Payment refuse, environ 5 % des cas).

Ou plus simplement avec le front : choisir le type, la date et l'heure (heure de Paris), puis « Réserver ».

À savoir :
- si Vehicles, Pricing ou Payment ne répond pas, l'étape 3 renvoie **502** et aucune place n'est consommée ;
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
$env:BOOKING_API_KEY = "<même valeur que API_KEY>"
.\.venv\Scripts\python -m streamlit run app.py
```

Sans Parking, remplir la capacité à la main (route admin) :
`$env:API_KEY = "..."; python scripts/seed_capacity.py --days 3`.

### Tests automatisés

```powershell
cd api/V1/booking
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```

Les tests utilisent une base SQLite jetable et une clé d'API de test : ils n'appellent aucun service réel
(Vehicles, Pricing, Payment et le bus sont remplacés par de faux adaptateurs, voir `tests/fakes.py`).

| Fichier | Ce qui est vérifié |
|---|---|
| `test_rules.py` | Règles de créneau : heures pleines, créneau passé, horizon de 30 jours, durée max 7 jours, conversion UTC. |
| `test_capacity.py` | Capacité par type et par heure : heure la plus chargée, pas de réservation partielle, libération, allocation sous le réservé refusée. |
| `test_reservation_flow.py` | Parcours métier : création, paiement accepté / refusé / en attente, pannes de Vehicles, Pricing, Payment et du bus, clé d'idempotence, annulation. |
| `test_access.py` | Les 10 cas de `GET /reservations/valid` (début inclus, fin exclue, fuseau, annulée, échouée, paiement accepté entre-temps...). |
| `test_api.py` | Routes HTTP : codes 201/404/409/422/502, validation des entrées, correlation ID, métriques Prometheus. |
| `test_security.py` | 401 sans clé ou avec une mauvaise clé sur chaque route, `/health` public, `/metrics` en Bearer, 500 sans détail, en-têtes HTTP. |

### Avec Docker Compose (API + front + Prometheus + Grafana)

Prérequis : `api/V1/booking/.env` rempli, et `.env` à la racine copié depuis `.env.example`
(clé d'API du front, mot de passe Grafana : compose refuse de démarrer s'ils manquent). Prometheus lit la clé de Booking dans
`monitoring/prometheus/secrets/booking_api_key` et le jeton d'Access dans `.../access_metrics_token`
(dossier ignoré par Git, un fichier = la valeur seule).

```powershell
docker compose up -d --build
```

| | URL |
|---|---|
| Booking | http://localhost:8000/docs |
| Front | http://localhost:8501 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / `GRAFANA_ADMIN_PASSWORD`, consultation anonyme en lecture seule) |

Base SQLite et logs dans un volume Docker : ils survivent à un `docker compose down` / `up`.
Démo de panne : `docker compose stop booking`, la cible passe à `up = 0` dans Grafana.
Le tableau de bord a une ligne **Latence** : p50 / p95 / p99 par service et p95 par route de Booking.

## Observabilité

**Correlation ID.** Chaque requête reçoit l'en-tête `X-Correlation-ID` (repris s'il est fourni, généré sinon),
renvoyé dans la réponse, écrit dans chaque ligne de log et transmis à Vehicles, Pricing, Payment, Parking et
dans les événements RabbitMQ. C'est un identifiant opaque, sans donnée personnelle.

**Logs.** Console, plus un fichier par jour dans `LOG_DIR` (14 jours de rétention).

**Métriques** (`GET /v2/booking/metrics`) :

| Métrique | Labels | Sens |
|---|---|---|
| `http_requests_total` | `method`, `route`, `status`, `outcome` | Trafic HTTP, `outcome` = `success` / `error` |
| `http_request_duration_seconds` | `method`, `route` | Histogramme de la durée de traitement, jusqu'à l'envoi de la réponse (hors tâches de fond). Seuils de 10 ms à 120 s : une réservation attend des services Render parfois en veille |
| `parking_operations_total` | `service="booking"`, `operation`, `result` | Réservations créées / refusées, paiements acceptés / refusés, annulations, vérifications Access valides / invalides, synchros de capacité |

Les noms suivent la convention commune du projet. `monitoring/prometheus/prometheus.yml` supervise aussi les
autres services sur Render et renomme à la lecture les métriques de Pricing et Vehicles pour qu'elles suivent
cette convention.

## Configuration

Variables d'environnement, ou fichier `api/V1/booking/.env` (jamais commité) :

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | Base de données : SQLite par défaut, Postgres en ligne (`postgresql://...` collée telle quelle) |
| `VEHICLES_SERVICE_URL`, `PRICING_SERVICE_URL`, `PAYMENT_SERVICE_URL`, `PARKING_SERVICE_URL` | URL des services |
| `VEHICLES_API_KEY`, `PRICING_API_KEY`, `PAYMENT_API_KEY`, `PARKING_API_KEY` | Clés **sortantes**, envoyées par Booking aux autres services dans `X-API-Key` (vide = pas d'en-tête) |
| `API_KEY` | Clé **entrante**, attendue par Booking sur les routes métier et `/metrics` (voir [Sécurité](#sécurité)). Vide = tout est refusé |
| `CLOUDAMQP_URL`, `EVENT_BUS_EXCHANGE` | Bus d'événements (vide = événements seulement écrits dans les logs) |
| `PAYMENT_POLL_INTERVAL_SECONDS`, `PAYMENT_POLL_TIMEOUT_SECONDS` | Suivi du paiement (5 s, 180 s) |
| `PARKING_SYNC_INTERVAL_SECONDS` | Synchronisation avec Parking (3600 s) |
| `HTTP_TIMEOUT_SECONDS` | Délai des appels sortants (120 s, le temps qu'un service Render se réveille) |
| `LOG_LEVEL`, `LOG_DIR`, `LOG_RETENTION_DAYS` | Niveau de log, dossier des fichiers de logs (vide = console seule, conseillé sur Render), rétention (14 jours) |

Côté front : `BOOKING_API_URL` et `BOOKING_API_KEY` (valeur de `API_KEY`).

## Déploiement (Render)

| | API | Front |
|---|---|---|
| Root Directory | `api/V1/booking` | `front` |
| Build Command | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
| Health Check | `/v2/booking/health` | — |

Variables à définir dans Render (onglet *Environment*) : celles de la section Configuration pour l'API,
`BOOKING_API_URL` et `BOOKING_API_KEY` pour le front.

**Données.** Le disque d'un service Render gratuit est effacé à chaque redémarrage : la base n'est donc pas un
fichier SQLite mais une base **Postgres** en ligne, désignée par `DATABASE_URL`. Les réservations et la capacité
survivent aux mises en veille et aux redéploiements (vérifié). `LOG_DIR` est laissé vide : les logs vont dans la
console, consultable dans l'onglet *Logs* de Render.

Chaque push sur `main` redéploie les deux services, une fois la CI GitHub Actions passée (auto-deploy Render
réglé sur *After CI Checks Pass*).

## Intégration continue (GitHub Actions)

`.github/workflows/ci.yml`, à chaque push et pull request :

| Job | Contrôle |
|---|---|
| Lint | `ruff check .` (configuration dans `ruff.toml`, API et front) |
| Tests | `pytest` sur l'API (base SQLite jetable, sans secret ni service externe) |
| Sécurité | SAST `bandit` sur le code, SCA `pip-audit` sur les dépendances de l'API et du front |
| Secrets | `gitleaks` sur **tout l'historique Git** : échoue si une clé, un mot de passe ou une URL avec identifiants a été commité, même supprimé depuis (valeurs masquées dans les logs) |
| Docker | Build des images API et front, puis l'image de l'API doit démarrer et répondre sur `/health` |

Le job Docker ne tourne que si les quatre autres passent. Pour que Render ne déploie qu'un commit dont la CI est verte,
régler *Settings → Build & Deploy → Auto-Deploy* sur **After CI Checks Pass** pour l'API et le front.

Mêmes contrôles en local :
```powershell
cd api/V1/booking
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m ruff check ../../..
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m bandit -r app
.\.venv\Scripts\python -m pip_audit -r requirements.txt
```

## Sécurité

**Authentification par clé d'API.** Une seule clé, `API_KEY`, lue dans les variables d'environnement (jamais
dans Git) et partagée avec les appelants de Booking : le front, Access et Prometheus.

| Accès | Routes |
|---|---|
| Clé exigée (`X-API-Key`) | toutes les routes métier : disponibilité, réservations, vérification Access, capacité, synchronisation |
| Clé exigée (`X-API-Key` ou `Authorization: Bearer`, format de Prometheus) | `/v2/booking/metrics` |
| Public | `GET /v2/booking/health` (health check Render), `/docs`, `/openapi.json` |

- Sans clé ou clé fausse : **401**.
- Comparaison en temps constant (`hmac.compare_digest`), clé jamais écrite dans les logs.
- Sans `API_KEY` configurée, les routes protégées refusent tout (le service **échoue fermé**) et le signalent au démarrage.
- Le front Streamlit appelle Booking côté serveur : la clé n'est jamais envoyée au navigateur.
- Générer une clé : `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

**Validation des entrées.** Schémas Pydantic : types de place limités à la nomenclature, dates contrôlées
(heures pleines, horizon, durée), e-mail validé, plaque limitée à 20 caractères (lettres, chiffres, espaces,
tirets), code de réservation à 6 chiffres, `vehicle_id` limité à 128 caractères, capacité positive.

**Erreurs.** Les erreurs métier renvoient un message court (`detail`). Une erreur imprévue renvoie
`500 {"detail": "Erreur interne du service Booking", "correlation_id": "..."}` : la trace complète reste dans
les logs, retrouvable par l'identifiant de corrélation. Les valeurs reçues (plaque, e-mail) ne sont jamais
journalisées.

**Secrets.** Fichiers `.env` et jetons Prometheus ignorés par Git, modèles `.env.example` sans valeur,
mot de passe Grafana et clé du front lus dans `.env` par Docker Compose, plus de secret par défaut dans le code.

**En-têtes HTTP.** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
et `Cache-Control: no-store` sur les réponses de l'API.

**Conteneurs.** API et front tournent avec un utilisateur sans privilèges ; image Prometheus en version fixe.

## Architecture

Architecture hexagonale : `domain/` (règles métier pures), `ports/` (interfaces), `application/` (cas d'usage),
`adapters/` (FastAPI, SQLAlchemy, httpx, RabbitMQ). Détails : [docs/booking_architecture.md](docs/booking_architecture.md).

Le problème technique propre au service est la **gestion d'une capacité dans le temps** : une réservation
consomme une place sur chaque heure de son créneau, et une seule heure saturée bloque tout le créneau.
