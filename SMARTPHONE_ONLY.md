# Utilisation 100 % smartphone

Ce mode est destiné à un opérateur qui ne possède pas de PC.

## Architecture recommandée

```text
Android / Chrome / Termux
        |
        | HTTPS
        v
VPS Linux
  - xbow-perso PWA
  - API FastAPI
  - workers
  - scanner Nuclei isolé
```

Le téléphone est l'interface et le poste d'administration. Les traitements lourds et les scanners restent sur un serveur Linux afin de conserver les garde-fous d'exécution de xbow-perso.

Ne pas utiliser Termux comme environnement de scan réel : Android/Termux ne reproduit pas le profil de sandbox Docker `restricted-v1`.

## 1. Depuis Android

Installer Termux depuis F-Droid ou GitHub Releases, puis :

```bash
pkg update
pkg install git openssh
```

Se connecter au VPS :

```bash
ssh USER@IP_DU_VPS
```

## 2. Sur le VPS

Le VPS doit disposer de Docker avec le plugin `docker compose`.

Cloner le dépôt :

```bash
git clone https://github.com/dbrckk/xbow-perso.git
cd xbow-perso
```

Lancer le bootstrap smartphone :

```bash
bash scripts/bootstrap-smartphone-vps.sh
```

Le script :
- crée `.env` s'il n'existe pas ;
- génère un `XBOW_API_TOKEN` fort si nécessaire ;
- force les valeurs initiales sûres ;
- laisse les scans actifs désactivés ;
- laisse la soumission HackerOne désactivée ;
- construit et démarre la PWA/API ;
- vérifie la santé du service.

## 3. Interface graphique sur Android

Dans Chrome Android, ouvrir :

```text
http://IP_DU_VPS:8080
```

Pour un usage permanent ou depuis Internet, utiliser le déploiement TLS du projet et ouvrir l'origine HTTPS configurée. Ne pas exposer durablement le port HTTP 8080 directement sur Internet.

La PWA contient notamment :
- Connexion HackerOne ;
- Pré-vol bug bounty réel ;
- revue du scope et de la policy ;
- campagnes ;
- findings et preuves ;
- validation ;
- rapports ;
- centre d'attention HackerOne.

## 4. Configurer HackerOne

Les secrets doivent rester sur le VPS. Ne pas les saisir dans le navigateur ni les committer.

Éditer `.env` depuis Termux/SSH :

```bash
nano .env
```

Configurer :

```text
XBOW_HACKERONE_API_USERNAME=...
XBOW_HACKERONE_API_TOKEN=...
```

Puis :

```bash
docker compose up -d
```

Au premier démarrage conserver :

```text
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_NUCLEI=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

## 5. Premier programme réel

Depuis la PWA :

1. ouvrir **Connexion HackerOne** ;
2. charger le programme exact ;
3. relire la policy actuelle ;
4. vérifier les assets in-scope et out-of-scope ;
5. confirmer explicitement si l'automatisation est autorisée ;
6. saisir une limite de requêtes égale ou inférieure à celle du programme ;
7. vérifier les comptes de test et exclusions ;
8. ouvrir **Pré-vol bug bounty réel**.

Seulement après cette revue, activer les verrous décrits dans `FIRST_REAL_HACKERONE_RUN.md`.

Pour le premier run :
- Nuclei uniquement ;
- sandbox `restricted-v1` ;
- PentAGI désactivé ;
- soumission HackerOne automatique désactivée ;
- validation et revue humaine avant rapport.

## 6. Administration depuis le téléphone

Commandes utiles :

```bash
cd ~/xbow-perso
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 scanner-worker
docker compose restart
git pull --ff-only
```

Démarrer le scanner uniquement après validation du programme :

```bash
docker compose --profile scanner up -d --build
```

Arrêt d'urgence :

```bash
sed -i 's/^XBOW_ENABLE_ACTIVE_SCANS=.*/XBOW_ENABLE_ACTIVE_SCANS=false/' .env
sed -i 's/^DRY_RUN=.*/DRY_RUN=true/' .env
docker compose stop scanner-worker
docker compose up -d
```

## 7. Ce qui n'est pas requis

Aucun PC n'est nécessaire. Tout peut être administré depuis :
- Chrome Android pour la PWA ;
- Termux pour SSH et les commandes serveur ;
- l'application GitHub ou github.com pour le dépôt.
