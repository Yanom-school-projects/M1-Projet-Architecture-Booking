# Journal — Service Booking

> Les entrées du 2 et du 3 septembre ont été reconstituées le 22 octobre à partir
> des dates de modification des fichiers et du contenu du code.

## 2 septembre

Fait
- cadrage métier du service rédigé (`docs/projet_fil_rouge_parking_cadrage_metier.md`) ;
- API FastAPI créée : `/health`, `/availability`, `/capacity`, `/reservations`, `/webhooks/payment` ;
- calendrier de capacité par type de place et par heure pleine (pas de place nominative) ;
- règles de créneau : heures pleines, horizon 30 jours, durée max 7 jours ;
- refus d'une réservation quand la capacité est épuisée sur une des heures du créneau ;
- mocks locaux de Vehicles, Pricing et Payment (`mocks/server.py`) ;
- paiement asynchrone : réservation `pending_payment`, puis `confirmed` ou `failed` via le webhook de Payment ;
- script de remplissage de la capacité (`scripts/seed_capacity.py`) en attendant Parking ;
- front Streamlit : vérifier la disponibilité, réserver, suivre le statut ;
- scénario de test bout en bout (`docs/booking_test_scenario.md`) ;
- Dockerfiles pour l'API et le front.

Problèmes
- aucun vrai service de l'équipe disponible : tout passe par les mocks.

Suite
- brancher les événements vers Messages ;
- fixer les contrats avec Pricing et Payment.

## 3 septembre

Fait
- code réorganisé en architecture hexagonale (domain / ports / application / adapters) ;
- erreurs métier traduites en codes HTTP au même endroit (409, 422, 404, 502) ;
- identifiant de réservation court à 6 chiffres (code donné au client) ;
- annulation d'une réservation confirmée avec remboursement de 50 % ;
- publication des événements sur RabbitMQ (CloudAMQP) : routing keys `booking.confirmed` et `booking.cancelled`, validées avec l'équipe Messages ;
- documentation d'architecture (`docs/booking_architecture.md`) et Swagger détaillé (version 0.2.0).

Problèmes
- le contrat de remboursement avec Payment n'est qu'une hypothèse posée côté Booking ;
- les règles métier disent qu'une réservation n'est pas annulable : l'annulation est hors cadrage ;
- le format du champ `event` attendu par Messages n'est pas confirmé.

Suite
- déployer sur Render ;
- remplacer les mocks par les vrais services.

## 22 octobre

Fait
- récupération des documents officiels « Règles métier » et « Rendu », comparaison avec le code ;
- code poussé sur GitHub, API et front déployés sur Render ;
- **Payment** (https://payment-xp8n.onrender.com) intégré et testé de bout en bout :
  - montant en centimes, `reference: {type: BOOKING, id}`, `source_service: booking`, en-tête `X-API-Key` ;
  - Payment ne rappelle pas Booking : Booking interroge `GET /payments/{id}` en tâche de fond toutes les 5 s, et à chaque consultation d'une réservation en attente ;
  - webhook `/webhooks/payment` supprimé (il permettait à n'importe qui de valider un paiement) ;
- **Pricing** (https://pricing-9khk.onrender.com) intégré : `POST /quote` avec zone, mode `reserved` et durée en minutes. Le `quote_id` est conservé pour la traçabilité de la grille ;
- **Parking** (https://parking-6r73.onrender.com) intégré : Booking lit le nombre de places réservables par catégorie au démarrage, puis toutes les heures, et l'applique aux 37 prochains jours (`POST /capacity/sync` pour forcer). Sur Render, la capacité se remplit donc toute seule après un redémarrage ;
- connexion RabbitMQ vérifiée (exchange `microservice-event-bus` présent) ;
- annulation conservée, mais **sans remboursement** : Payment ne gère pas les remboursements ;
- `/health` renvoie la version (0.3.0) ;
- correctifs trouvés en testant :
  - deux vérifications simultanées publiaient deux fois `reservation.confirmed` : le changement de statut est maintenant atomique ;
  - l'API ne démarrait plus quand le `.env` contenait des variables inconnues ;
  - Vehicles absent ou en panne donnait une erreur 500, maintenant une erreur 502 avec un message clair ;
  - une date avec fuseau (`+02:00`) donnait une erreur 500 ; tout est maintenant ramené en UTC et le front envoie l'heure de Paris ;
  - la recherche de disponibilité ne validait pas le créneau, et une recherche sur un an créait 8 760 lignes en base ;
  - `PUT /capacity` acceptait une heure non pleine et une capacité inférieure aux places déjà réservées ;
  - l'erreur d'origine d'un échec Pricing/Payment n'était pas journalisée.

Problèmes
- Vehicles n'a pas encore d'URL : en ligne, la création de réservation renvoie 502 tant qu'il manque ;
- un appel à Payment a échoué une fois sans réponse (coupure ou délai dépassé), sans pouvoir en savoir plus à ce moment-là : c'est désormais journalisé ;
- Parking expose le nombre de places réservables **libres à l'instant T**, pas un quota par créneau : à clarifier avec l'équipe Parking ;
- pas de tests automatisés, pas de CI, routes sensibles non protégées ;
- `docs/booking_architecture.md` et `docs/booking_test_scenario.md` décrivent encore l'ancien fonctionnement.

Suite
- brancher Vehicles dès qu'il a une URL, et tester le parcours complet en ligne ;
- ajouter un endpoint pour Access (réservation valable à un instant donné) ;
- protéger les routes sensibles par clé d'API ;
- tests pytest et pipeline CI.

## 28 octobre

Fait
- **Access** : nouvel endpoint `GET /reservations/active?vehicle_id=...&at=...` (version 0.4.0) :
  - une réservation est valable si elle est `confirmed` et que l'instant est dans son créneau (`start_at <= at < end_at`) ;
  - `at` est facultatif (par défaut : maintenant) et accepte une date avec fuseau, comme le reste de l'API ;
  - réponse toujours 200 : `{vehicle_id, at, valid, reservations}`, avec pour chaque réservation le code, le type de place et le créneau. Access sait donc quel type de place attribuer ;
  - l'e-mail du client n'est pas renvoyé : Access n'en a pas besoin ;
  - une réservation encore `pending_payment` sur ce créneau est d'abord revérifiée auprès de Payment. Si le suivi en tâche de fond a été coupé (redémarrage), un client qui a payé n'est pas bloqué à l'entrée ;
- pas de tolérance d'avance ou de retard : ces cas sont hors périmètre dans le cadrage métier ;
- `GET /reservations?vehicle_id=...` reste disponible comme historique, mais n'est plus la route indiquée à Access ;
- testé sur une base temporaire (10 cas) : début du créneau inclus, fin exclue, arrivée en avance, date avec fuseau, réservation annulée ou échouée, paiement accepté entre-temps, paiement toujours en attente, véhicule inconnu ;
- correctif du front : un `/` final dans `BOOKING_API_URL` faisait appeler `//reservations` (404 `Not Found` sur Render) ;
- **mode secours temporaire pour Vehicles** (`VEHICLES_FALLBACK_ENABLED=true`) : si Vehicles ne répond pas, Booking calcule lui-même l'identifiant du véhicule au lieu de renvoyer 502. Ce n'est pas la plaque : c'est une empreinte HMAC-SHA256 préfixée `tmp-`. Désactivé par défaut, à retirer quand Vehicles est branché.

Problèmes
- le contrat n'est pas encore validé avec l'équipe Access (forme de la réponse, `vehicle_id` ou plaque en entrée) ;
- la route n'est pas protégée : n'importe qui connaissant un `vehicle_id` peut savoir s'il a une réservation ;
- les réservations créées en mode secours ont un identifiant `tmp-...` différent de celui que donnera Vehicles : Access ne pourra pas les retrouver.

Suite
- envoyer le contrat à l'équipe Access et tester avec leur service ;
- protéger `/reservations/active` par une clé d'API réservée à Access ;
- supprimer le mode secours Vehicles dès que Vehicles a une URL ;
- reprendre ces 10 cas dans les tests pytest.

## 24 novembre — revue de code et d'intégration

Fait
- **persistance** : `DATABASE_URL` accepte une URL Postgres (Neon / Render) collée telle quelle, forcée sur psycopg 3, avec vérification des connexions mises en veille (`pool_pre_ping`) ;
- **Vehicles branché** : appel de `POST /api/vehicle/create`, le `code` renvoyé est stocké comme identifiant pseudonymisé ;
- **nomenclature commune des types de place** (`STANDARD`, `HANDICAPPED`, `ELECTRIC`, `XL`, `TWO_WHEELS`) alignée sur Parking, sans correspondance propre à Booking ;
- délai des appels sortants passé de 60 à 120 s : un service Render gratuit en veille met parfois plus d'une minute à répondre.

Problèmes
- les réveils successifs des services Render rallongent fortement le premier parcours de réservation.

Suite
- traçabilité (correlation ID) et observabilité.

## 25 novembre — traçabilité et observabilité

Fait
- **logs** : console + un fichier par jour (`LOG_DIR`, 14 jours de rétention), erreurs journalisées avec leur cause ;
- **correlation ID** `X-Correlation-ID` : repris ou généré à l'entrée, présent dans chaque ligne de log, renvoyé dans la réponse, transmis à Vehicles, Pricing, Payment, Parking et dans les événements RabbitMQ, et conservé avec la réservation pour le suivi du paiement en tâche de fond ;
- **idempotence du paiement** : la clé d'idempotence est conservée avec la réservation, un nouvel essai ne crée plus un second paiement chez Payment ;
- **API** : toutes les routes sous `/v2/booking`, routes de capacité renommées (`/capacity-slots/...`), README, docs et front mis à jour ;
- **métriques Prometheus** sur `/v2/booking/metrics` : `http_requests_total` (méthode, route, code, succès/erreur) et `parking_operations_total` (réservations, paiements, annulations, vérifications Access, synchros de capacité) ;
- **stack de supervision locale** (`docker-compose.yml`) : Booking + front + Prometheus + Grafana ; Prometheus supervise aussi les autres services sur Render ; les métriques de Pricing et Vehicles sont renommées à la lecture pour suivre la convention commune ; le jeton du `/metrics` d'Access est monté depuis un fichier ignoré par Git.

Problèmes
- chaque service avait sa propre convention de nommage des métriques : il a fallu s'entendre sur `http_requests_total` / `parking_operations_total` ;
- pas encore de mesure de la durée des requêtes.

Suite
- CI/CD et sécurisation.

## 27 novembre

Fait
- consignes de fin de projet récupérées (`consignes/`), analyse de l'écart avec le code : [todolist.md](todolist.md) ;
- README mis à jour (URL Render, état de maturité, observabilité, Docker Compose) ;
- **sécurisation (version 2.5.0)** :
  - une clé d'API unique (`API_KEY`, en-tête `X-API-Key`) sur toutes les routes métier, partagée avec le front et Access ; 401 sans clé ou clé fausse ; seul `/health` reste public ;
  - `/metrics` protégé par la même clé, acceptée aussi en `Authorization: Bearer` pour Prometheus (lue depuis un fichier ignoré par Git) ;
  - comparaison en temps constant, jamais de clé dans les logs, tout refusé si la clé n'est pas configurée ;
  - une clé par appelant avec des droits différents a été envisagée puis écartée : trop lourd pour le besoin, une clé suffit à ne plus exposer le service librement ;
  - entrées resserrées : plaque (20 caractères, lettres/chiffres/espaces/tirets), `vehicle_id` (128 caractères), code d'annulation vérifié dans le front avant de construire l'URL ;
  - erreur imprévue : réponse 500 générique avec l'identifiant de corrélation, détail seulement dans les logs ;
  - plus de secret par défaut : mode secours Vehicles coupé sans `VEHICLES_FALLBACK_SECRET`, mot de passe Grafana et clé du front lus dans un `.env` ;
  - en-têtes de sécurité HTTP, conteneurs API et front non-root, image Prometheus en version fixe ;
  - vérifié avec un script TestClient : 401 sans clé ou clé fausse sur chaque route, 200 avec la clé, `/metrics` en X-API-Key et en Bearer, plaque invalide, 500 sans détail.
- **tests automatisés pytest** (110 tests, `api/V1/booking/tests/`, lancés par `python -m pytest`) :
  - base SQLite jetable et faux adaptateurs Vehicles / Pricing / Payment / bus : l'architecture hexagonale permet de tester le métier réel sans réseau ;
  - règles de créneau, capacité par heure, parcours de réservation (paiement accepté, refusé, en attente, issue inconnue renvoyée avec la même clé, pannes de chaque service) ;
  - les 10 cas Access du 28 octobre repris sur `GET /reservations/valid` ;
  - sécurité (401 sur chaque route, `/health` public, Bearer pour `/metrics`, 500 sans détail), correlation ID et métriques Prometheus.
- **intégration continue** (`.github/workflows/ci.yml`) à chaque push et pull request :
  - lint `ruff` (règles communes à l'API et au front dans `ruff.toml`), tests `pytest` ;
  - SAST `bandit` et SCA `pip-audit` (API et front) ;
  - build des deux images Docker, puis démarrage de l'API et appel de `/health` ;
  - le déploiement reste l'auto-deploy de Render, à régler sur « After CI Checks Pass » pour attendre la CI ;
- bandit a relevé que le code de réservation était tiré avec `random` : il sert à consulter et annuler une réservation, il est maintenant tiré avec `secrets`.

Problèmes
- la clé doit être transmise à l'équipe Access, sinon leurs vérifications reçoivent 401 ;
- tant que Render n'est pas réglé sur « After CI Checks Pass », un commit qui casse la CI est quand même déployé.

Suite
- régler l'auto-deploy Render sur la CI, vérifier la première exécution du workflow sur GitHub.

---

## Point d'étape au 28 octobre

### État par aspect de maturité

0 = non commencé, 1 = en cours, 2 = fonctionnel, 3 = maîtrisé

| Aspect | État | Constat |
|---|---|---|
| Métier | 2 | Capacité dans le temps, créneaux et cycle de vie conformes aux règles. Écart assumé : l'annulation (sans remboursement). |
| API / Déploiement | 2 | Déployé sur Render, `/health` avec version, Swagger en ligne. Base SQLite non persistante. |
| Intégration | 2 | Payment, Pricing, Parking et RabbitMQ réels. Endpoint Access prêt, pas encore testé avec leur service. Il manque Vehicles (pas d'URL). |
| Interface | 2 | Front Streamlit en heure de Paris : disponibilité, réservation, suivi, annulation. |
| Qualité | 1 | Logs, erreurs propres (422/404/409/502), configuration par variables d'environnement. Aucun test automatisé, pas de `/metrics`. |
| CI/CD | 1 | Redéploiement automatique sur Render à chaque push sur `main`, mais sans tests. |
| Sécurité | 0 | Aucune route protégée. Secrets hors de Git, clé envoyée à Payment. |

### Fonctionnalités

- [x] Je peux consulter les disponibilités d'un type de place sur un créneau.
- [x] Je peux réserver une place sur un créneau (heures pleines, 30 jours max à l'avance, 7 jours max de durée).
- [x] Je peux empêcher de réserver plus de places que la capacité disponible.
- [x] Je récupère auprès de Parking le nombre de places proposées à la réservation.
- [x] Je peux demander le prix à Pricing.
- [x] Je peux faire payer la réservation avec Payment.
- [ ] Je peux obtenir l'identifiant pseudonymisé du véhicule auprès de Vehicles (pas encore d'URL).
- [x] Messages est prévenu quand une réservation est confirmée ou annulée (événement RabbitMQ).
- [x] Je peux annuler une réservation confirmée (sans remboursement).
- [x] Access peut vérifier qu'un véhicule possède une réservation valable *maintenant* (`GET /reservations/active`).

### Reste à faire (par priorité)

**1. Intégration**
- [ ] Vehicles : renseigner `VEHICLES_SERVICE_URL` et vérifier le contrat (`POST /resolve` → `{vehicle_id}`).
- [x] Access : endpoint dédié `GET /reservations/active?vehicle_id=...&at=...`, qui ne renvoie que les réservations `confirmed` couvrant l'instant donné.
- [ ] Access : faire valider le contrat par l'équipe Access et tester avec leur service.
- [ ] Parking : savoir si `spot_available` (booking) est un quota ou un nombre de places libres maintenant.
- [ ] Messages : confirmer le format du champ `event` (`RESERVATION_CONFIRMED`).
- [ ] Tester le parcours complet en ligne (front Render → Booking → Vehicles/Pricing/Payment → Messages).

**2. Sécurité**
- [ ] Clé d'API pour les routes appelées par les autres services (lecture des réservations par Access).
- [ ] Clé admin pour `PUT /capacity`, `POST /capacity/sync` et `GET /reservations` sans filtre (expose les e-mails de tous les clients).
- [ ] Laisser publics seulement `/health`, `/availability`, `POST /reservations` et `GET /reservations/{id}`.

**3. Qualité**
- [ ] Tests pytest : `domain/rules.py`, `CapacityService`, scénario complet avec faux adaptateurs (réservation → ACCEPTED → confirmed).
- [ ] `/metrics`, si le temps le permet.

**4. CI/CD**
- [ ] GitHub Actions : lancer les tests à chaque push ; ne déployer sur Render que si les tests passent.

**5. Déploiement**
- [ ] Base Postgres sur Render pour garder les réservations entre deux redémarrages.

**6. Rendus**
- [x] `README.md`.
- [ ] Mettre à jour `docs/booking_architecture.md` et `docs/booking_test_scenario.md`.
- [ ] Remplir la ligne Booking du tableau de suivi collectif.

### Écarts avec les règles métier

- **Annulation** : les règles (§2.7) disent qu'une réservation « n'est pas annulable ou modifiable », mais la fiche Booking (§3.5) parle d'« annuler ». Choix : annulation conservée, sans remboursement. Elle libère seulement la place. À présenter comme une extension.
- **Horizon de 30 jours** : la règle ajoute les jours réservables un par un à minuit. Le code utilise une fenêtre glissante de 30 jours à partir de l'heure courante. L'écart est faible mais réel.
- **Fuseau horaire** : réglé. L'API travaille en UTC et accepte les dates avec fuseau ; le front saisit l'heure de Paris.
