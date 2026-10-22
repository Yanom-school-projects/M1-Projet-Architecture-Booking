# Projet fil rouge – Gestion d’un parking

## 1. Principe général

Le système gère un seul parking.

Ce parking accueille des véhicules français. Les plaques d’immatriculation peuvent être considérées comme valides dès lors qu’elles respectent le format choisi pour l’exercice.

Le système doit permettre de gérer le cycle de vie principal d’un véhicule dans le parking :

1. un véhicule se présente à l’entrée ;
2. le système identifie le véhicule ;
3. le système vérifie s’il peut entrer ;
4. le véhicule entre et occupe sa place ;
5. le véhicule reste stationné ;
6. au moment de la sortie, le coût du stationnement est calculé ;
7. le paiement est effectué ;
8. le véhicule est autorisé à sortir ;
9. les documents utiles peuvent être produits et transmis au client.

Le système doit aussi permettre de réserver une place à l’avance.

Le parking possède plusieurs types de places :

- Standard ;
- XL ;
- Handicapé ;
- Électrique.

Le prix dépend de la place occupée et des règles tarifaires en vigueur.

Le système est découpé en plusieurs microservices. Chaque microservice possède une responsabilité métier claire et reste responsable de ses propres données.

L’objectif du projet n’est pas seulement de faire fonctionner plusieurs API. Il faut que chaque service ait un rôle identifiable, que les responsabilités soient séparées et que les échanges entre services correspondent à un besoin métier.

---

## 2. Règles métier générales

### 2.1. Parking

Le système gère un seul parking.

Le parking possède une capacité limitée.

Chaque place possède un identifiant unique.

Chaque place possède un type parmi :

- Standard ;
- XL ;
- Handicapé ;
- Électrique ;
- 2 roues.

Une place peut être disponible pour une entrée immédiate (walk-in) ou réservée au catalogue de réservation.

Le nombre de places proposées à la réservation peut évoluer.

Une place peut donc passer du catalogue réservé au catalogue walk-in, et inversement.

Les places sont gérées par nombre disponible par catégorie. Il n'y a pas d'affectation d'une place nominalement.

---

## 2.2. Véhicules

Chaque véhicule possède un identifiant interne pseudonymisé.

La plaque réelle est connue du service Vehicles.

Les autres services doivent utiliser autant que possible l’identifiant pseudonymisé du véhicule.

La plaque réelle ne doit pas circuler entre les microservices sans nécessité fonctionnelle.

Un véhicule peut posséder des informations utiles à l’accès, par exemple :
- Electrique
- Handicapé
- XL
- 2 ou 4 roues

Le détail exact de ces informations pourra être ajusté pendant le projet.

---

## 2.3. Accès

Un véhicule ne peut entrer que si une place du type demandée est accessible.

Le service Access décide si l’entrée est autorisée.

Il s’appuie pour cela sur les informations fournies par les autres services.

Pour le projet, on considère qu’un véhicule autorisé à entrer occupe effectivement la place qui lui a été attribuée.

La détection physique réelle de la place occupée est hors périmètre.

Les règles métier s'appliquent :
- un véhicule déjà présent dans le parking ne peut pas entrer une seconde fois ;
- un véhicule qui n’est pas présent dans le parking ne peut pas sortir ;
- un 2 roues peut occuper une place 4 roues ;
- un 4 roues ne peut occuper une place 2 roues ;
- un véhicule électrique peut occuper une place non-électrique ;
- un véhicule non-électrique ne peut occuper une place électrique ;
- un véhicule XL ne peut occuper un autre type de place
- un véhicule handicapé peut occuper une place handicapé ou XL
- seul un véhicule handicapé peut occuper une place handicapé

---

## 2.4. Stationnement

Un stationnement commence lorsque l’entrée du véhicule est confirmée.

Un stationnement se termine lorsque la sortie est confirmée.

Un stationnement est associé au minimum à :

- un véhicule pseudonymisé ;
- une date et heure d’entrée ;
- une date et heure de sortie lorsque le stationnement est terminé.

La durée du stationnement sert au calcul du prix lorsque cela est nécessaire.

La durée du stationnement est plafonnée à sept jours.

---

## 2.5. Tarification

Le prix est calculé à partir de règles tarifaires.

Les règles dépendent des éléments suivants :
- type de place ;
- durée ;
- réservation ou entrée immédiate.

Le temps est facturé par quart d'heure. Tout quart d'heure entamé est dû.

Le service Pricing est responsable du calcul du prix.

Il doit aussi garantir la traçabilité de la grille tarifaire utilisée.

Un prix calculé doit donc pouvoir être relié à une version précise des règles tarifaires.

Une modification de la grille ne doit pas empêcher de comprendre comment un ancien prix a été obtenu.

---

## 2.6. Paiement

Le service Payment ne calcule pas les prix.

Il reçoit un montant à payer et une référence permettant de comprendre ce qui est payé.

Un paiement possède son propre identifiant.

Un paiement possède un statut.

Les statuts du paiement sont les suivants :

- créé ;
- en attente ;
- payé ;
- refusé ;
- annulé ;
- remboursé.

Un même paiement ne doit pas être exécuté plusieurs fois par erreur.

Le service Payment doit donc garantir l’idempotence des demandes de paiement.

Un appel répété pour la même opération ne doit pas provoquer plusieurs encaissements.

---

## 2.7. Réservation

Une partie des places du parking peut être proposée à la réservation.

Une réservation correspond à une demande pour :

- un type de place ;
- une date et heure de début ;
- une date et heure de fin.

Le service Booking doit être capable de savoir si une place du type demandé est disponible sur tout le créneau.

Pour le projet initial, on considère que les véhicules respectent les horaires prévus.

Les cas suivants sont donc hors périmètre pour l’instant :

- arrivée en avance ;
- arrivée en retard ;
- absence du client ;
- dépassement important de l’heure de sortie ;
- prolongation de réservation.

Une réservation confirmée consomme une capacité future du parking.

Le service Booking ne réserve pas nécessairement une place physique précise longtemps à l’avance. Il peut gérer un nombre de places disponibles par type et par période.

La durée maximum d'une réservation est celle d'un stationnement (voir règle métier du stationnement).

Les créneaux sont réservables par tranches d'une heure, alignées sur les heures pleines.

Il n'est pas possible de réserver un créneau et plus de trente jours à l'avance. Les jours réservables sont ajoutés un par un quotidiennement à minuit. L'heure en cours est réservable, facturée pleine.

Le paiement est fait au moment de la commande.

Pour les besoins de l'exercice, une réservation n'est pas annulable ou modifiable.

---

## 2.8. Documents et notifications

Le système peut produire différents documents ou messages utiles au client :


Le service Messages reçoit les informations produites par les autres services et génère les documents ou messages correspondants.

Il doit être capable de traiter des événements asynchrones.

---

# 3. Microservices

## 3.1. Parking

### Rôle du service

Gérer les quantités de places disponibles par type.

### Cœur de métier attendu

Parking est l’autorité sur le stock de places.

Il connait les quantités de places :

- disponibles ;
- occupées ;
- proposées à la réservation ;
- proposées en walk-in.

Il doit permettre de faire évoluer la répartition entre :

- capacité réservée à à la réservation ;
- capacité disponible pour les entrées immédiates.

Le cœur technique du service est donc la gestion d’un stock limité et concurrent.

### Objets

A définir.

### Workflow simple

Entrée :

1. Access demande une place d’un certain type.
2. Parking cherche une place disponible.
3. Une fois la place disponible devenue occupée, le véhicule peut entrer.

Sortie :

1. le véhicule quitte le parking ;
2. Parking libère la place ;
3. la place redevient disponible selon son mode de commercialisation.

Gestion du stock :

1. une partie des places est affectée à Booking ;
2. une autre partie reste disponible en walk-in ;
3. cette répartition peut être modifiée (modalités à définir pour éviter d'impacter les créneaux déjà réservés)

---

## 3.2. Vehicles

### Nom

Vehicles

### Rôle du service

Gérer l’identité des véhicules et protéger les informations directement identifiantes.

### Cœur de métier attendu

Vehicles est le service de référence pour les véhicules.

Il connaît la plaque réelle.

Il produit et conserve un identifiant pseudonymisé utilisé par les autres services.

Il doit éviter que les autres microservices manipulent inutilement les plaques réelles.

Il peut également conserver les informations nécessaires à l’accès au parking.

Le cœur technique du service est la maîtrise des données personnelles et la pseudonymisation.

### Objets

Véhicule :

- identifiant pseudonymisé ;
- plaque réelle ;
- caractéristiques utiles ;
- statut éventuel.

Lien d’identité :

- plaque réelle ;
- identifiant pseudonymisé.

### Workflow simple

Identification :

1. un véhicule se présente avec sa plaque ;
2. Vehicles recherche ou crée son identifiant pseudonymisé ;
3. Vehicles renvoie l’identifiant pseudonymisé ;
4. les autres services utilisent ensuite cet identifiant.

Consultation :

1. un service demande une information utile sur un véhicule ;
2. Vehicles répond avec uniquement les informations nécessaires.

---

## 3.3. Pricing

### Nom

Pricing

### Rôle du service

Calculer le prix d’un stationnement ou d’une réservation selon une grille tarifaire identifiable.

### Cœur de métier attendu

Pricing possède les règles de tarification.

Il reçoit les informations nécessaires au calcul.

Il calcule un montant.

Il doit être capable de gérer plusieurs règles de prix afin que le calcul ne se résume pas à une simple multiplication.

Les règles peuvent évoluer pendant le projet.

Pricing doit garantir la traçabilité de la règle appliquée.

Chaque calcul doit donc permettre de savoir :

- quelle grille a été utilisée ;
- quelle version de cette grille a été utilisée ;
- quelles données ont conduit au montant obtenu.

Le cœur technique du service est le versionnement et la traçabilité des référentiels tarifaires.

### Objets

Grille tarifaire :

- identifiant ;
- version ;
- date de début de validité ;
- règles.

Calcul de prix :

- identifiant ;
- contexte du calcul ;
- montant ;
- version de grille utilisée ;
- date du calcul.

### Workflow simple

Calcul d’un stationnement :

1. un service transmet les informations nécessaires ;
2. Pricing sélectionne la grille applicable ;
3. Pricing calcule le prix ;
4. Pricing conserve la référence de la grille utilisée ;
5. Pricing renvoie le montant et la référence du calcul.

Calcul d’une réservation :

1. Booking demande le prix d’un créneau ;
2. Pricing applique la grille correspondante ;
3. Pricing renvoie le montant ;
4. Booking peut ensuite demander le paiement.

Changement de tarif :

1. une nouvelle grille est créée ;
2. elle remplace l’ancienne pour les nouveaux calculs ;
3. les anciens calculs restent rattachés à l’ancienne version.

---

## 3.4. Payment

### Nom

Payment

### Rôle du service

Gérer le cycle de vie d’un paiement et garantir qu’une même demande n’est pas encaissée plusieurs fois.

### Cœur de métier attendu

Payment reçoit un montant déjà calculé.

Il ne décide pas du prix.

Il crée une opération de paiement.

Il suit son état.

Il doit garantir l’idempotence.

Si un autre service envoie plusieurs fois la même demande de paiement, Payment doit reconnaître qu’il s’agit de la même opération et ne pas créer deux encaissements.

Il doit conserver un historique suffisamment clair pour comprendre ce qui s’est passé.

Le paiement peut être entièrement simulé dans le cadre du projet.

Le cœur technique du service est l’idempotence et la gestion correcte du cycle de vie d’une transaction.

### Objets

Paiement :

- identifiant ;
- montant ;
- statut ;
- date de création ;
- date de mise à jour.

Clé d’idempotence :

- identifiant fourni par le demandeur ;
- paiement associé.

Tentative de paiement :

- identifiant ;
- paiement ;
- date ;
- résultat.

### Workflow simple

Création :

1. un service demande un paiement ;
2. Payment vérifie si cette demande a déjà été traitée ;
3. si elle existe déjà, il retourne le paiement existant ;
4. sinon, il crée un nouveau paiement ;
5. le paiement est simulé ;
6. Payment met à jour son statut.

Réservation :

1. Booking obtient un prix auprès de Pricing ;
2. Booking demande le paiement ;
3. Payment traite la demande ;
4. Payment confirme le résultat ;
5. Booking confirme ensuite la réservation.

Sortie :

1. le montant du stationnement est calculé ;
2. une demande de paiement est envoyée avec l'identifiant du stationnement concerné ;
3. Payment traite le paiement ;
4. le résultat est communiqué au service concerné.

---

## 3.5. Booking

### Nom

Booking

### Rôle du service

Gérer la disponibilité future du parking et les réservations sur des créneaux horaires.

### Cœur de métier attendu

Booking gère un calendrier de disponibilité.

Il connaît le nombre de places réservables par type.

Il doit répondre à une question simple :

« Pour ce type de place, entre telle heure et telle heure, reste-t-il une capacité disponible ? »

Il doit éviter que trop de réservations soient acceptées sur un même créneau.

Il doit pouvoir créer, confirmer ou annuler une réservation.

Il travaille avec Pricing pour obtenir le prix.

Il travaille avec Payment pour le paiement anticipé.

Le cœur technique du service est la gestion de capacité dans le temps.

### Objets

Réservation :

- identifiant ;
- véhicule pseudonymisé ;
- type de place ;
- date et heure de début ;
- date et heure de fin ;
- statut ;
- prix éventuel ;
- paiement éventuel.

Capacité réservée :

- type de place ;
- période ;
- nombre de places disponibles pour Booking.

### Workflow simple

Recherche :

1. le client demande un type de place et un créneau ;
2. Booking vérifie la capacité disponible ;
3. Booking répond si la réservation est possible.

Création :

1. Booking reçoit une demande ;
2. Booking vérifie la disponibilité ;
3. Booking demande un prix à Pricing ;
4. Booking demande un paiement à Payment ;
5. si le paiement est validé, Booking confirme la réservation.

Utilisation :

1. le véhicule se présente à l’entrée ;
2. Access vérifie auprès de Booking s’il possède une réservation valable ;
3. la réservation est prise en compte dans la décision d’accès.

Gestion de capacité :

1. Parking définit combien de places sont disponibles pour Booking ;
2. Booking utilise cette capacité dans son calendrier ;
3. cette capacité peut évoluer.

---

## 3.6. Messages

### Nom

Messages

### Rôle du service

Produire les documents et messages destinés au client à partir des événements du système.

### Cœur de métier attendu

Messages reçoit des informations produites par les autres services.

Il peut recevoir ces informations de manière asynchrone.

Il transforme ces informations en documents ou en messages.

Exemples :
- notification de paiement
- notification de réservation
- ticket d'entrée (walk-in et réservation)
- justificatif de paiement (idem)

Le service doit pouvoir produire un document exploitable, par exemple un PDF.

Le cœur technique du service est la consommation de messages asynchrones et la génération de documents.

### Objets

Notification :

- identifiant ;
- type ;
- destinataire ou référence client ;
- contenu ;
- statut ;
- date de création.

Document :

- identifiant ;
- type ;
- données utilisées ;
- fichier généré ;
- date de génération.

### Workflow simple

Réservation :

1. Booking confirme une réservation ;
2. Messages reçoit l’information ;
3. Messages génère une confirmation ;
4. le document ou message est mis à disposition.

Paiement :

1. Payment confirme un paiement ;
2. Messages reçoit l’information ;
3. Messages génère un reçu.

Entrée ou sortie :

1. Access ou un autre service produit un événement ;
2. Messages le reçoit ;
3. Messages génère le document correspondant.

---

## 3.7. Access

### Nom

Access

### Rôle du service

Décider si un véhicule peut entrer ou sortir et coordonner les échanges nécessaires avec les autres services.

### Cœur de métier attendu

Access est le point central du workflow d’entrée et de sortie.

Il ne possède pas les données métier des autres services.

Il interroge les services responsables lorsque cela est nécessaire.

À l’entrée, il doit notamment pouvoir déterminer :

- quel véhicule se présente ;
- s’il est autorisé ;
- s’il possède une réservation ;
- quel type de place doit lui être attribué ;

À la sortie, il doit coordonner les informations nécessaires au calcul et au paiement du stationnement.

Access peut également consommer des événements produits par les autres services.

Le cœur technique du service est la coordination de plusieurs services et l’ingestion d’événements.

### Objets

Demande d’accès :

- identifiant ;
- véhicule ;
- type : entrée ou sortie ;
- date ;
- statut.

Autorisation d’accès :

- identifiant ;
- demande associée ;
- résultat ;
- motif ;

Événement d’accès :

- véhicule entré ;
- véhicule sorti ;
- accès refusé ;
- autre événement utile.

### Workflow simple

Entrée :

1. un véhicule se présente ;
2. Access demande à Vehicles son identifiant pseudonymisé et les informations utiles ;
3. Access vérifie si une réservation existe auprès de Booking OU demande une place à Parking ;
6. Access autorise l’entrée ;
8. Parking passe la place en état occupé ;
9. Access publie ou transmet l’information d’entrée aux services intéressés.

Sortie :

1. un véhicule demande à sortir ;
2. Access identifie le stationnement en cours ;
3. les informations nécessaires au calcul sont envoyées à Pricing ;
4. Pricing renvoie le montant ;
5. un paiement est demandé à Payment ;
6. Payment confirme le paiement ;
7. Access autorise la sortie ;
8. Parking libère la place ;
9. Access publie ou transmet l’information de sortie.

Réservation :

1. un véhicule avec réservation se présente ;
2. Access récupère son identité pseudonymisée ;
3. Access vérifie la réservation auprès de Booking ;
4. Access demande à Parking (?) l’attribution d’une place adaptée ;
5. Access autorise l’entrée.

---

# 4. Exigences communes à tous les microservices

Chaque microservice doit au minimum disposer :

- d’un nom clair ;
- d’une responsabilité métier clairement définie ;
- d’une API REST lorsque des appels directs sont nécessaires ;
- de flux asynchrones lorsque cela est pertinent ;
- d’une documentation de ses interfaces ;
- d’un système de logs ;
- d’un endpoint `/health`.

Le choix entre appel REST et message asynchrone doit être justifié par le besoin.

Un service peut utiliser les deux.

Un appel direct est adapté lorsqu’un service a besoin d’une réponse pour continuer son traitement.

Un message asynchrone est adapté lorsqu’un service annonce qu’un fait s’est produit sans avoir besoin d’attendre immédiatement le travail des autres services.

---

# 5. Hors périmètre pour le premier MVP

Les sujets suivants sont volontairement exclus dans un premier temps :

- panne d’un microservice ;
- panne du broker ;
- reprise après incident ;
- fonctionnement dégradé ;
- traitement manuel des erreurs ;
- détection physique réelle des véhicules sur chaque place ;
- véhicule garé volontairement sur une mauvaise place ;
- retard sur une réservation ;
- arrivée en avance ;
- no-show ;
- prolongation automatique de réservation ;
- plusieurs parkings ;
- gestion réelle d’une banque ou d’un prestataire de paiement.

Ces sujets pourront être ajoutés ensuite comme évolutions du projet.

---

# 6. Questions attendues pour chaque service

Chaque étudiant doit être capable de répondre simplement aux questions suivantes :

1. Quel est le nom de mon service ?
2. Quelle est sa responsabilité métier ?
3. Quelles données possède-t-il ?
4. Quelles données ne doit-il pas posséder ?
5. Quels objets métier manipule-t-il ?
6. Quelles actions principales sait-il réaliser ?
7. Quels autres services doit-il appeler ?
8. Quels services doivent l’appeler ?
9. Quels événements produit-il ?
10. Quels événements consomme-t-il ?
11. Quelle partie du workflow dépend directement de lui ?
12. Quel est le problème technique particulier que mon service doit traiter ?

Le but est que chaque microservice soit compréhensible indépendamment, tout en participant à un workflow commun.
