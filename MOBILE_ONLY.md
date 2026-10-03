# xbow-perso depuis Android uniquement

Ce mode opératoire suppose **aucun PC**. Le téléphone Android sert à piloter GitHub, ouvrir la PWA et, uniquement pour l'initialisation ou le dépannage du serveur, ouvrir une session SSH mobile.

## Architecture recommandée

```text
Android
  |
  +-- navigateur -> interface xbow-perso
  +-- GitHub -> code, Actions, logs de déploiement
  +-- SSH mobile -> maintenance ponctuelle
                     |
                     v
                VPS Linux
                     |
                     +-- Docker Compose
                     +-- backend
                     +-- frontend/PWA
                     +-- workers
                     +-- scanner worker (désactivé par défaut)
```

Le téléphone ne doit pas exécuter les scanners lourds. Il reste l'interface opérateur.

## 1. Serveur requis

Utiliser un VPS Linux x86_64 ou arm64 capable d'exécuter Docker et Docker Compose. Le compte d'exploitation doit pouvoir gérer Docker.

Depuis une application SSH Android, utiliser le bootstrap maintenu du dépôt :

```bash
curl -fsSL https://raw.githubusercontent.com/dbrckk/xbow-perso/main/scripts/bootstrap-mobile-ubuntu.sh -o /tmp/xbow-bootstrap.sh
sudo bash /tmp/xbow-bootstrap.sh
```

Le bootstrap installe Docker/Compose si nécessaire, clone ou actualise `/opt/xbow-perso`, génère un `XBOW_API_TOKEN` aléatoire et démarre uniquement la stack de base avec les verrous sûrs fermés. Le token initial est écrit temporairement dans `/root/xbow-bootstrap-secrets.txt` (mode 600).

Le lire une fois depuis SSH, le stocker dans un gestionnaire de mots de passe sur Android, puis supprimer ce fichier :

```bash
sudo cat /root/xbow-bootstrap-secrets.txt
sudo rm /root/xbow-bootstrap-secrets.txt
```

Le baseline doit rester :

```env
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_NUCLEI=false
XBOW_ENABLE_RECON=false
XBOW_ENABLE_EXTERNAL_RECON=false
XBOW_ENABLE_BROWSER_AUTOMATION=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

Ne pas transformer `.env` en profil live permanent. Les scripts production utilisent un overlay root-only séparé pour l'armement Nuclei.

## 2. Interface graphique sur Android

L'interface est la PWA xbow-perso.

- accès local au serveur : `http://SERVER_IP:8080`
- accès Internet : utiliser **HTTPS** ou un VPN privé ; ne pas exposer durablement le port 8080 en HTTP public
- avec l'overlay TLS du repo, utiliser l'origine HTTPS configurée

Depuis Chrome/Firefox Android, ouvrir cette origine. On peut ensuite utiliser **Ajouter à l'écran d'accueil** pour obtenir un comportement proche d'une application.

Commencer par le panneau **Pré-vol bug bounty réel**.

## 3. Déploiement depuis l'application GitHub ou le navigateur Android

Le workflow `mobile-vps-deploy` permet de mettre à jour le serveur sans PC.

Créer dans les secrets/environnements GitHub les valeurs suivantes :

- `XBOW_DEPLOY_HOST` : nom DNS ou IP du VPS
- `XBOW_DEPLOY_USER` : utilisateur SSH
- `XBOW_DEPLOY_SSH_KEY` : clé privée dédiée au déploiement
- `XBOW_DEPLOY_KNOWN_HOSTS` : ligne known_hosts vérifiée du serveur

Le workflow utilise l'environnement GitHub `mobile-vps`.

Ensuite, depuis Android :

1. ouvrir le repo `dbrckk/xbow-perso` sur GitHub ;
2. ouvrir **Actions** ;
3. choisir **mobile-vps-deploy** ;
4. **Run workflow** ;
5. laisser `main` comme ref ;
6. suivre les logs directement depuis le téléphone.

Le workflow met à jour `/opt/xbow-perso`, reconstruit la stack de base et vérifie que les trois verrous critiques restent fermés :

```env
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

Il ne démarre pas le profil scanner.

## 4. Connexion HackerOne depuis la PWA

Configurer sur le VPS :

```env
XBOW_API_TOKEN=<secret long>
XBOW_HACKERONE_API_USERNAME=<identifiant API HackerOne>
XBOW_HACKERONE_API_TOKEN=<token HackerOne>
```

Redémarrer la stack puis ouvrir la PWA sur Android.

Dans **Connexion HackerOne** :

1. charger le programme exact ;
2. lire la policy actuelle ;
3. confirmer uniquement les assets explicitement in-scope ;
4. vérifier les exclusions ;
5. vérifier si l'automatisation est autorisée ;
6. saisir le plafond de requêtes du programme ;
7. effectuer la preview.

## 5. Passage au scanner réel

Ne pas éditer manuellement les verrous live dans `.env`. Après revue du programme exact dans la PWA et uniquement si sa policy autorise l'automatisation, utiliser le chemin d'armement maintenu :

```bash
sudo bash /opt/xbow-perso/scripts/mobile-enable-hackerone-nuclei.sh
```

Ce script :
- remet d'abord le VPS sur le `main` courant et le baseline sûr ;
- refuse l'armement si la file ou un batch est encore actif ;
- conserve `.env` en fail-safe ;
- écrit le profil live dans `/root/xbow-live-scanner.env` avec permissions privées ;
- limite le moteur à Nuclei et au profil sandbox `restricted-v1` ;
- garde la soumission HackerOne désactivée ;
- vérifie readiness, API HackerOne et verdict final avant de déclarer le runtime prêt.

La PWA doit afficher **PRÊT SCAN RÉEL** avant toute exécution. PentAGI reste désactivé.

## 6. Arrêt immédiat depuis Android

Utiliser le désarmement maintenu :

```bash
sudo bash /opt/xbow-perso/scripts/mobile-disable-hackerone-nuclei.sh
```

Ce script supprime le profil live root-only puis redéploie le baseline fail-safe. Vérifier ensuite :

```bash
sudo bash /opt/xbow-perso/scripts/mobile-production-status.sh
```

La sortie doit confirmer que le profil scanner est désarmé et que les gates live sont de nouveau fermés.

## Ce qui nécessite encore une action manuelle

Le repo peut être préparé automatiquement, mais il faut encore fournir un serveur distant et ses accès. Aucun PC n'est nécessaire : la création du VPS, l'ajout des secrets GitHub, le lancement des Actions et l'exploitation de la PWA peuvent tous être faits depuis Android.


## 7. Passage en production distribuée depuis Android

Pour une installation durable, utiliser les scripts de migration plutôt que d'improviser la configuration PostgreSQL/Redis/TLS :

```bash
sudo bash /opt/xbow-perso/scripts/mobile-production-preflight.sh
sudo bash /opt/xbow-perso/scripts/mobile-production-cutover.sh
sudo bash /opt/xbow-perso/scripts/mobile-production-status.sh
```

Le preflight est en lecture seule et refuse de continuer si les gates sûrs ne sont pas fermés. Le cutover migre vers PostgreSQL/Redis et démarre la stack distribuée sans profil scanner. En cas de problème après migration, utiliser `mobile-production-rollback.sh`.

Le vault reste une étape séparée via `mobile-vault-cutover.sh`, avec son rollback dédié. Ne jamais copier ni afficher dans un chat les fichiers root-only de secrets.
