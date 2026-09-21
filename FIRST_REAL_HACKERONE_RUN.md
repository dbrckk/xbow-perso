# Premier vrai bug bounty HackerOne avec xbow-perso

Ce guide décrit le passage du mode préparation au premier programme HackerOne réel.

## 1. Ouvrir l'interface

- même machine : `http://localhost:8080`
- téléphone sur le même réseau : `http://IP_DU_SERVEUR:8080`
- serveur distant : utiliser l'origine HTTPS configurée

Dans la PWA, commencer par **Pré-vol bug bounty réel**.

## 2. Configurer les secrets côté serveur

Ne jamais mettre les secrets HackerOne dans le navigateur, un commit ou un fichier partagé.

Configurer :

```bash
XBOW_API_TOKEN=<secret long>
XBOW_HACKERONE_API_USERNAME=<identifiant API HackerOne>
XBOW_HACKERONE_API_TOKEN=<token HackerOne>
```

Le vault xbow est recommandé pour HackerOne lorsque le déploiement permanent est prêt.

Laisser au départ :

```bash
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_NUCLEI=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

Redémarrer les services puis cliquer **Revérifier**.

## 3. Charger un programme HackerOne

Dans **Connexion HackerOne** :

1. rechercher le programme ;
2. sélectionner le programme exact ;
3. cliquer pour le charger ;
4. vérifier que le snapshot distant et le scope sont affichés.

Ne pas continuer si le programme n'est pas celui prévu.

## 4. Revue humaine obligatoire

Lire la policy HackerOne actuelle et confirmer dans l'interface :

- Safe Harbor / autorisation ;
- automation autorisée ou non ;
- assets in-scope ;
- assets out-of-scope ;
- exclusions techniques ;
- limite exacte de requêtes ;
- contraintes de compte de test ;
- autres restrictions du programme.

L'interface ne déduit jamais automatiquement l'autorisation de scanner.

## 5. Ouvrir les verrous de scan réel

Seulement après la revue précédente, utiliser le script d'activation persistant :

```bash
sudo bash /opt/xbow-perso/scripts/mobile-enable-hackerone-nuclei.sh
```

Ce script conserve le baseline sûr dans `.env`, crée le profil scanner réel séparé, vérifie que la file est idle, arme Nuclei 3.11.1 dans le sandbox `restricted-v1` et laisse la soumission HackerOne désactivée.

Retourner dans **Pré-vol bug bounty réel** puis cliquer **Revérifier**.

Le statut doit être **PRÊT SCAN RÉEL** avant toute exécution réelle. Le serveur refusera aussi le lancement si ce pré-vol n'est plus valide au moment exact du clic.

## 6. Preview finale et READY

Avant le lancement :

1. prévisualiser les règles exécutables ;
2. relire les cibles autorisées et refusées ;
3. vérifier le plafond de requêtes ;
4. confirmer manuellement la preview ;
5. enregistrer le profil de revue lié au fingerprint courant ;
6. vérifier que le programme apparaît `READY` dans le catalogue.

Le serveur refait une vérification distante juste avant le lancement. Un changement de fingerprint, de scope ou d'état du programme force une nouvelle revue au lieu de démarrer avec une autorisation périmée.

## 7. Premier run recommandé

Pour le premier run réel :

- commencer avec 1 à 3 programmes `READY`, avec bounty ;
- garder le mode **À la suite** pour simplifier la première observation ;
- utiliser **Auto-select** ou **Auto Queue** après avoir vérifié les choix ;
- conserver uniquement Nuclei dans l'allowlist scanner ;
- garder le sandbox `restricted-v1` ;
- ne pas activer PentAGI ;
- ne pas activer la soumission HackerOne automatique ;
- garder un plafond de requêtes conservateur égal ou inférieur à la limite du programme.

Une fois le lot enregistré côté serveur, il continue sans que le dashboard reste ouvert. Pour un lot séquentiel, chaque membre est à nouveau vérifié auprès de HackerOne juste avant son démarrage. Si HackerOne est temporairement indisponible, le membre reste en attente et sera retenté ; si le programme ou son fingerprint a réellement changé, il passe en `review`.

À la réouverture de la PWA, le lot actif est repris automatiquement. Un lot terminé avec des membres à revoir ou bloqués reste visible avec sa raison.

## 8. Après un finding

Un finding ne doit pas être soumis automatiquement.

Le flux attendu est :

1. preuve enregistrée ;
2. validation indépendante ;
3. revue humaine ;
4. confirmation du finding ;
5. génération du brouillon HackerOne ;
6. téléchargement et contrôle du brouillon ;
7. soumission manuelle au début.

La soumission directe peut rester désactivée avec :

```bash
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

## Arrêt immédiat

Si le scope, la policy, la limite de requêtes ou l'autorisation ne sont plus certains :

```bash
XBOW_ENABLE_ACTIVE_SCANS=false
DRY_RUN=true
```

Puis désarmer proprement le profil scanner :

```bash
sudo bash /opt/xbow-perso/scripts/mobile-disable-hackerone-nuclei.sh
```

