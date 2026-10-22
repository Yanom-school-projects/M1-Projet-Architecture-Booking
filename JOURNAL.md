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
- récupération des documents officiels « Règles métier » et « Rendu » ;
- comparaison du code avec ces documents et point d'étape (ci-dessous) ;
- code poussé sur GitHub ;
- **intégration réelle avec Payment** (https://payment-xp8n.onrender.com) testée de bout en bout :
  - montant envoyé en centimes, `reference: {type: BOOKING, id}`, `source_service: booking`, en-tête `X-API-Key` ;
  - Payment ne rappelle pas Booking : Booking interroge `GET /payments/{id}` en tâche de fond toutes les 5 s, et à chaque consultation d'une réservation en attente ;
  - `ACCEPTED` → `confirmed` + événement `reservation.confirmed`, `REFUSED` → `failed` + place libérée ;
  - webhook `/webhooks/payment` supprimé (il permettait à n'importe qui de valider un paiement) ;
- bug corrigé : deux vérifications simultanées publiaient deux fois `reservation.confirmed`. Le changement de statut est maintenant atomique en base ;
- annulation conservée, mais **sans remboursement** : Payment ne gère pas les remboursements ;
- mock Payment aligné sur le vrai contrat, pour travailler en local.

Problèmes
- service pas encore déployé : pas d'URL publique ni de Swagger en ligne ;
- pas de tests, pas de CI/CD, pas encore de protection de nos propres routes ;
- `docs/booking_architecture.md` et `docs/booking_test_scenario.md` décrivent encore l'ancien fonctionnement (webhook, remboursement de 50 %).

Suite
- déployer sur Render avec les URL des vrais services ;
- brancher Vehicles, Pricing, Parking et Access dès réception de leurs URL ;
- voir la liste « Reste à faire ».

---

## Point d'étape au 22 octobre

### État par aspect de maturité

0 = non commencé, 1 = en cours, 2 = fonctionnel, 3 = maîtrisé

| Aspect | État | Constat |
|---|---|---|
| Métier | 2 | Capacité dans le temps, créneaux et cycle de vie conformes aux règles. Seul écart : l'annulation, que les règles excluent (§2.7). |
| API / Déploiement | 1 | `/health`, Swagger et version 0.2.0 en local. Non déployé sur Render. |
| Intégration | 1 | Payment réel et RabbitMQ branchés. Vehicles et Pricing sont encore des mocks. Parking et Access ne sont pas encore connectés. |
| Interface | 2 | Front Streamlit pour réserver, suivre le statut et annuler. |
| Qualité | 1 | Logs simples, erreurs propres, configuration par variables d'environnement. Aucun test, pas de `/metrics`. |
| CI/CD | 0 | Pas de pipeline. Le dossier n'est pas un dépôt git en local. |
| Sécurité | 0 | Aucune authentification. Les secrets sont dans `.env`, ignoré par git (c'est bien). |

### Fonctionnalités (à reprendre dans le README)

- [x] Je peux consulter les disponibilités d'un type de place sur un créneau.
- [x] Je peux réserver une place sur un créneau (heures pleines, 30 jours max à l'avance, 7 jours max de durée).
- [x] Je peux empêcher de réserver plus de places que la capacité disponible.
- [x] Parking peut définir la capacité réservable par type et par heure (testé avec le script, pas avec le vrai Parking).
- [ ] Je peux demander le prix à Pricing (fonctionne avec le mock seulement).
- [x] Je peux faire payer la réservation avec Payment (vrai service, testé le 22 octobre).
- [ ] Je peux obtenir l'identifiant pseudonymisé du véhicule auprès de Vehicles (mock seulement).
- [x] Messages est prévenu quand une réservation est confirmée (événement RabbitMQ).
- [ ] Access peut vérifier qu'un véhicule possède une réservation valable *maintenant*. Aujourd'hui, Access ne peut que lister toutes les réservations du véhicule et doit filtrer lui-même.

### Reste à faire (par priorité)

**1. Déploiement (API / Déploiement)**
- [x] Mettre le code sur GitHub.
- [ ] Déployer l'API et le front sur Render. Passer à Postgres via `DATABASE_URL` : le SQLite de Render est effacé à chaque redéploiement.
- [ ] Renseigner `PAYMENT_API_KEY` dans les variables d'environnement Render (jamais dans Git).
- [ ] Ajouter la version dans `/health` (ex. `{"status": "ok", "version": "0.2.0"}`).

**2. Intégration réelle (Intégration)**
- [ ] Valider avec Vehicles : `POST /resolve` → `{vehicle_id}`.
- [ ] Valider avec Pricing : `POST /reservation` → `{amount, price_reference}`.
- [x] Valider avec Payment : contrat réel intégré (polling, centimes, `X-API-Key`).
- [ ] Valider avec Parking : qui appelle `PUT /capacity`, à quel moment, et comment éviter de réduire la capacité sous le nombre de places déjà réservées.
- [ ] Ajouter pour Access un endpoint dédié, par exemple `GET /reservations/active?vehicle_id=...&at=...`, qui ne renvoie que les réservations `confirmed` couvrant l'instant donné.
- [ ] Confirmer avec Messages le format du champ `event` (`RESERVATION_CONFIRMED`).
- [ ] Remplacer les URL des mocks par celles des vrais services dans les variables d'environnement Render.

**3. Sécurité**
- [ ] Clé d'API (variable d'environnement) pour les appels entre services : `PUT /capacity` (Parking), lecture des réservations par Access.
- [x] Clé `X-API-Key` envoyée à Payment (prête pour le jour où Payment l'activera).
- [ ] Clé admin pour `PUT /capacity` et `GET /reservations` sans filtre, qui expose aujourd'hui les emails de tous les clients.
- [ ] Laisser publics seulement `/health`, `/availability` et `POST /reservations`.

**4. Qualité**
- [ ] Tests unitaires de `domain/rules.py` et de `CapacityService` (pytest).
- [ ] Tests de l'API avec `TestClient` et de faux adaptateurs (scénario complet : réservation → webhook paid → confirmed).
- [ ] Logs structurés sur les appels sortants (durée, code HTTP).
- [ ] `/metrics`, si le temps le permet.

**5. CI/CD**
- [ ] GitHub Actions : lancer les tests à chaque push.
- [ ] Déploiement automatique sur Render une fois les tests passés sur `main`.

**6. Rendus**
- [ ] Mettre à jour `docs/booking_architecture.md` et `docs/booking_test_scenario.md` (polling Payment, annulation sans remboursement).
- [ ] `README.md` : rôle, version, URL déployée, URL Swagger, dépendances, comment tester, fonctionnalités.
- [ ] Tenir ce journal à jour chaque jour de travail.
- [ ] Remplir la ligne Booking du tableau de suivi collectif.

### Écarts avec les règles métier à trancher

- **Annulation** : les règles (§2.7) disent qu'une réservation « n'est pas annulable ou modifiable », mais la fiche Booking (§3.5) parle d'« annuler ». Choix du 22 octobre : annulation conservée, sans remboursement (Payment n'en gère pas). Elle libère seulement la place. À présenter comme une extension.
- **Horizon de 30 jours** : la règle ajoute les jours réservables un par un à minuit. Le code utilise une fenêtre glissante de 30 jours à partir de l'heure courante. L'écart est faible mais réel.
- **Fuseau horaire** : l'API compare les dates à l'heure UTC alors que le front envoie l'heure locale (Paris, +1/+2 h). À vérifier sur la règle « l'heure en cours est réservable ».
