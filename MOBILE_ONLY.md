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

Depuis une application SSH Android, préparer une seule fois le serveur :

```bash
sudo mkdir -p /opt/xbow-perso
sudo chown "$USER":"$USER" /opt/xbow-perso
git clone https://github.com/dbrckk/xbow-perso.git /opt/xbow-perso
cd /opt/xbow-perso
cp .env.example .env
```

Configurer ensuite les secrets uniquement dans `/opt/xbow-perso/.env`. Ne jamais les écrire dans GitHub, une issue ou un chat.

Pour le premier démarrage, conserver :

```env
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_NUCLEI=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

Puis :

```bash
docker compose up -d --build
docker compose ps
```

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

Ne modifier les verrous qu'après revue du programme.

```env
XBOW_ENABLE_ACTIVE_SCANS=true
DRY_RUN=false
XBOW_ENABLE_NUCLEI=true
XBOW_NUCLEI_ALLOWED_VERSION=3.11.1
XBOW_SCANNER_ALLOWED_ENGINES=nuclei
XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1
```

Puis depuis SSH Android :

```bash
cd /opt/xbow-perso
docker compose --profile scanner up -d --build
```

La PWA doit afficher **PRÊT SCAN RÉEL** avant une exécution.

Pour le premier programme, garder PentAGI et la soumission HackerOne automatique désactivés.

## 6. Arrêt immédiat depuis Android

Depuis SSH Android :

```bash
cd /opt/xbow-perso
sed -i 's/^XBOW_ENABLE_ACTIVE_SCANS=.*/XBOW_ENABLE_ACTIVE_SCANS=false/' .env
sed -i 's/^DRY_RUN=.*/DRY_RUN=true/' .env
docker compose stop scanner-worker || true
docker compose up -d
```

Vérifier ensuite dans la PWA que le pré-vol indique de nouveau le mode bloqué/sûr.

## Ce qui nécessite encore une action manuelle

Le repo peut être préparé automatiquement, mais il faut encore fournir un serveur distant et ses accès. Aucun PC n'est nécessaire : la création du VPS, l'ajout des secrets GitHub, le lancement des Actions et l'exploitation de la PWA peuvent tous être faits depuis Android.
