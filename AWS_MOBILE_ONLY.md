# AWS mobile-only bootstrap

This path is for operating xbow-perso with **Android only**. AWS EC2 runs the containers; the phone is only the operator interface.

## Why AWS for the first remote host

AWS explicitly permits hosting security-assessment tooling in AWS IP space for authorized third-party testing, subject to its penetration-testing policy and acceptable-use rules. Do not use xbow-perso for denial of service, uncontrolled scanning, or targets outside the exact HackerOne authorization.

For new AWS customers, the Free Tier may provide promotional credits. Check the current AWS offer and billing dashboard before creating resources.

## 1. Create the EC2 host from Android

From the AWS Console in your Android browser:

1. Open **EC2 > Instances > Launch instances**.
2. Name: `xbow-perso`.
3. Image: **Ubuntu Server 24.04 LTS**.
4. Architecture: `x86_64` is the simplest default. `arm64` is also supported by the pinned Nuclei scanner image.
5. Start with at least **2 vCPU / 4 GiB RAM**. More RAM is useful once Playwright/scanners run concurrently.
6. Create/download an SSH key pair and store it securely on Android.
7. Security group:
   - SSH/22: restrict to your current IP whenever practical.
   - Do **not** expose port 8080 permanently to the public Internet.
   - expose 443 only after HTTPS is configured.
8. Launch the instance.

Do not enable active scans yet.

## 2. Connect from Android

Use an SSH client on Android. Connect as the Ubuntu user:

```bash
ssh ubuntu@EC2_PUBLIC_IP
```

## 3. Install xbow-perso

On the server:

```bash
curl -fsSL https://raw.githubusercontent.com/dbrckk/xbow-perso/main/scripts/bootstrap-mobile-ubuntu.sh -o /tmp/xbow-bootstrap.sh
sudo bash /tmp/xbow-bootstrap.sh
```

The bootstrap:

- installs Docker + Compose;
- clones `dbrckk/xbow-perso` into `/opt/xbow-perso`;
- generates a random `XBOW_API_TOKEN`;
- keeps `DRY_RUN=true`;
- keeps active scans disabled;
- keeps Nuclei disabled;
- keeps HackerOne automatic submission disabled;
- builds and starts only the base stack.

The generated API token is stored root-only at:

```text
/root/xbow-bootstrap-secrets.txt
```

Read it once from SSH:

```bash
sudo cat /root/xbow-bootstrap-secrets.txt
```

Store it in a secure password manager on Android. After confirming it is saved:

```bash
sudo rm /root/xbow-bootstrap-secrets.txt
```

## 4. Configure HackerOne credentials

Edit the server-side environment:

```bash
cd /opt/xbow-perso
sudo nano .env
```

Set:

```env
XBOW_HACKERONE_API_USERNAME=<your HackerOne API identifier>
XBOW_HACKERONE_API_TOKEN=<your HackerOne API token>
```

Keep:

```env
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_NUCLEI=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

Then:

```bash
sudo docker compose up -d
```

## 5. Open the GUI safely

The GUI is the xbow-perso PWA.

For temporary initial verification, use an SSH tunnel from an Android SSH client that supports local port forwarding:

```text
local 8080 -> 127.0.0.1:8080 on the EC2 host
```

Then open:

```text
http://127.0.0.1:8080
```

For regular remote use, configure the repository TLS/reverse-proxy overlay or a private VPN and use HTTPS. Do not leave raw port 8080 open to the Internet.

## 6. First HackerOne program

From the PWA:

1. open **Connexion HackerOne**;
2. load the exact program;
3. review the current policy;
4. confirm only explicit in-scope assets;
5. verify exclusions and account requirements;
6. verify that automation/scanning is permitted;
7. enter a request-rate ceiling no higher than the program allows;
8. preview the executable scope/rules.

Only after this review may the live gates be changed.

## 7. Enable the scanner only for an authorized program

On the server:

```env
XBOW_ENABLE_ACTIVE_SCANS=true
DRY_RUN=false
XBOW_ENABLE_NUCLEI=true
XBOW_NUCLEI_ALLOWED_VERSION=3.11.1
XBOW_SCANNER_ALLOWED_ENGINES=nuclei
XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1
```

Then:

```bash
cd /opt/xbow-perso
sudo docker compose --profile scanner up -d --build
```

The PWA must show **PRÊT SCAN RÉEL** before execution.

## 8. Emergency stop from Android

```bash
cd /opt/xbow-perso
sudo sed -i 's/^XBOW_ENABLE_ACTIVE_SCANS=.*/XBOW_ENABLE_ACTIVE_SCANS=false/' .env
sudo sed -i 's/^DRY_RUN=.*/DRY_RUN=true/' .env
sudo docker compose stop scanner-worker || true
sudo docker compose up -d
```

Re-open the PWA and verify that live readiness is blocked again.


## Production migration preflight from a phone

After the production-migration and vault-migration features are merged, a mobile operator can prepare PostgreSQL + Redis and run the **read-only migration plan** with one pasteable command:

```bash
sudo bash /opt/xbow-perso/scripts/mobile-production-preflight.sh
```

The script first refuses to continue unless all safe execution gates remain closed:

```text
DRY_RUN=true
XBOW_ENABLE_ACTIVE_SCANS=false
XBOW_ENABLE_NUCLEI=false
XBOW_ENABLE_HACKERONE_SUBMISSION=false
```

It then updates `main`, validates the distributed Compose configuration, generates PostgreSQL/Redis credentials into the root-only file `/root/xbow-production-secrets.env`, starts **only** PostgreSQL and Redis, and runs the SQLite → PostgreSQL/Redis migration **plan**.

It does not start scanner services, does not perform the migration, and does not change any scan or HackerOne submission gate.

Do not display, copy into chat, or screenshot `/root/xbow-production-secrets.env`.


## Storage cutover from a phone

Run the preflight first and confirm it ends with `PRE-FLIGHT COMPLETE`. When the migration plan is clean, the actual storage cutover is one command:

```bash
sudo bash /opt/xbow-perso/scripts/mobile-production-cutover.sh
```

The cutover script refuses to run unless the four safe gates remain closed. It then:

1. updates `main`;
2. verifies PostgreSQL and Redis health;
3. runs one final read-only migration plan;
4. stops backend/worker/frontend/TLS and any optional worker that happens to be running;
5. runs the quiesced SQLite → PostgreSQL/Redis migration;
6. preserves the original SQLite source and migration backup;
7. starts the distributed backend/worker/frontend/TLS stack **without scanner profiles**;
8. waits for backend health and runs readiness;
9. checks HTTPS when `XBOW_PUBLIC_HOST` is configured.

If migration apply fails, the script automatically restarts the previous SQLite stack.

If the migration succeeds but the distributed stack later fails validation, use:

```bash
sudo bash /opt/xbow-perso/scripts/mobile-production-rollback.sh
```

The rollback stops distributed application services and restarts the original SQLite application stack. It does not delete PostgreSQL/Redis data, so diagnosis or a later retry remains possible.

The storage cutover does **not** migrate or enable the encrypted vault. Vault cutover remains a separate step after the distributed storage stack is verified.


## Vault cutover from a phone

After the PostgreSQL/Redis storage cutover has completed and the distributed backend is healthy, migrate legacy application credentials into the encrypted vault with:

```bash
sudo bash /opt/xbow-perso/scripts/mobile-vault-cutover.sh
```

The script:

1. requires the successful storage-migration marker;
2. verifies the four safe execution gates remain closed;
3. runs a redacted vault migration plan directly from the private server `.env`;
4. encrypts and verifies the legacy API/HackerOne/provider/TOTP/audit/browser secrets;
5. verifies the vault-backed API token before changing `.env`;
6. creates `.env.pre-vault.bak` with private permissions;
7. removes migrated legacy secret assignments and enables the file-backed vault;
8. restarts only the safe distributed services;
9. verifies vault-backed authentication, backend readiness and HTTPS.

The master key is generated inside the private `xbow-data` volume at `/data/vault-master.key`; its value is never printed.

If the vault-enabled restart fails, the script restores the pre-vault environment automatically. A manual rollback is also available:

```bash
sudo bash /opt/xbow-perso/scripts/mobile-vault-rollback.sh
```

The rollback restores the legacy-secret `.env` while preserving the encrypted vault files for diagnosis or retry. Neither command enables scanner, PentAGI, Nuclei, or HackerOne submission profiles.
