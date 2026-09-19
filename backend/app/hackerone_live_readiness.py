from __future__ import annotations

import os
from typing import Any

from .deployment_preflight import build_deployment_preflight
from .hackerone_client import HackerOneClientError, load_hackerone_credentials
from .runtime_capabilities import safe_scanner_runtime_capability


def _strict_bool(name: str, default: bool = False) -> tuple[bool, bool]:
    raw = os.getenv(name)
    if raw is None:
        return default, True
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True, True
    if value in {"0", "false", "no", "off"}:
        return False, True
    return default, False


def _configured(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def build_hackerone_live_readiness(
    dependencies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return redacted readiness for an operator-reviewed real HackerOne run."""

    deployment = build_deployment_preflight(dependencies)
    scanner = safe_scanner_runtime_capability()

    try:
        load_hackerone_credentials()
        credentials_configured = True
    except HackerOneClientError:
        credentials_configured = False

    submission_enabled, submission_valid = _strict_bool(
        "XBOW_ENABLE_HACKERONE_SUBMISSION",
        False,
    )
    report_sync_enabled, report_sync_valid = _strict_bool(
        "XBOW_ENABLE_HACKERONE_REPORT_SYNC",
        False,
    )

    checks = [
        {
            "id": "hackerone_credentials",
            "label": "Credentials HackerOne serveur",
            "required": True,
            "ok": credentials_configured,
            "action": (
                "Configurer hackerone_api_username et hackerone_api_token dans le vault "
                "ou les variables serveur legacy lorsque le vault est désactivé."
            ),
        },
        {
            "id": "core_dependencies",
            "label": "Dépendances principales",
            "required": True,
            "ok": bool(deployment.get("dependencies_ready")),
            "action": "Corriger /api/ready avant tout test réel.",
        },
        {
            "id": "active_scans",
            "label": "Scans actifs explicitement autorisés",
            "required": True,
            "ok": bool(scanner.get("active_scans_enabled")),
            "action": "Définir XBOW_ENABLE_ACTIVE_SCANS=true seulement après revue du programme.",
        },
        {
            "id": "dry_run_disabled",
            "label": "Mode dry-run désactivé",
            "required": True,
            "ok": scanner.get("dry_run") is False,
            "action": "Définir DRY_RUN=false uniquement au moment du passage en réel.",
        },
        {
            "id": "scanner_worker",
            "label": "Worker scanner dédié",
            "required": True,
            "ok": bool(scanner.get("scanner_worker_enabled")),
            "action": "Démarrer le profil Docker scanner et garder le worker dédié.",
        },
        {
            "id": "nuclei_enabled",
            "label": "Nuclei activé",
            "required": True,
            "ok": bool(scanner.get("nuclei_enabled")),
            "action": "Définir XBOW_ENABLE_NUCLEI=true après revue de la policy.",
        },
        {
            "id": "restricted_sandbox",
            "label": "Sandbox scanner restricted-v1",
            "required": True,
            "ok": scanner.get("sandbox_profile") == "restricted-v1",
            "action": "Conserver XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1.",
        },
        {
            "id": "nuclei_allowlisted",
            "label": "Nuclei dans l'allowlist scanner",
            "required": True,
            "ok": bool(scanner.get("nuclei_allowlisted")),
            "action": "Conserver nuclei dans XBOW_SCANNER_ALLOWED_ENGINES.",
        },
        {
            "id": "nuclei_version",
            "label": "Version Nuclei explicitement approuvée",
            "required": True,
            "ok": bool(scanner.get("nuclei_version_configured")),
            "action": (
                "Définir XBOW_NUCLEI_ALLOWED_VERSION=3.11.1 pour correspondre "
                "à l'image scanner actuellement pinnée."
            ),
        },
        {
            "id": "scanner_dispatch",
            "label": "Admission scanner complète",
            "required": True,
            "ok": bool(scanner.get("dispatch_ready")) and bool(scanner.get("nuclei_enabled")),
            "action": "Résoudre tous les dispatch_block_reasons du scanner.",
        },
        {
            "id": "api_token",
            "label": "Token API xbow configuré",
            "required": True,
            "ok": _configured("XBOW_API_TOKEN"),
            "action": "Configurer XBOW_API_TOKEN avec un secret long côté serveur.",
        },
        {
            "id": "report_sync",
            "label": "Suivi distant des reports",
            "required": False,
            "ok": report_sync_valid and report_sync_enabled,
            "action": (
                "Optionnel mais recommandé : XBOW_ENABLE_HACKERONE_REPORT_SYNC=true "
                "et profil hackerone-sync."
            ),
        },
        {
            "id": "direct_submission",
            "label": "Soumission directe HackerOne",
            "required": False,
            "ok": submission_valid and submission_enabled,
            "action": (
                "Optionnel : laisser désactivé au début, ou activer seulement "
                "après validation du workflow d'approbation humaine."
            ),
        },
    ]

    required = [item for item in checks if item["required"]]
    required_ok = all(bool(item["ok"]) for item in required)
    configuration_valid = submission_valid and report_sync_valid
    if not configuration_valid:
        required_ok = False
        checks.append(
            {
                "id": "boolean_configuration",
                "label": "Configuration booléenne valide",
                "required": True,
                "ok": False,
                "action": (
                    "Corriger XBOW_ENABLE_HACKERONE_SUBMISSION et "
                    "XBOW_ENABLE_HACKERONE_REPORT_SYNC."
                ),
            }
        )

    program_review_ready = (
        credentials_configured
        and bool(deployment.get("dependencies_ready"))
        and deployment.get("status") != "error"
    )

    operator_steps = [
        {
            "id": "configure_access",
            "title": "Configurer l'accès local xbow",
            "when": "setup",
            "done": _configured("XBOW_API_TOKEN"),
            "instruction": (
                "Configurer XBOW_API_TOKEN côté serveur, démarrer xbow-perso, "
                "puis ouvrir l'interface graphique sur le port 8080 ou son origine HTTPS."
            ),
        },
        {
            "id": "configure_hackerone",
            "title": "Connecter HackerOne",
            "when": "setup",
            "done": credentials_configured,
            "instruction": (
                "Créer/récupérer l'identifiant API et le token HackerOne, puis les "
                "configurer uniquement côté serveur (vault recommandé)."
            ),
        },
        {
            "id": "select_program",
            "title": "Choisir un programme réel",
            "when": "program",
            "done": False,
            "instruction": (
                "Dans l'interface, rechercher puis charger le programme HackerOne exact "
                "sur lequel tu veux travailler."
            ),
        },
        {
            "id": "review_program",
            "title": "Relire la policy et le scope",
            "when": "program",
            "done": False,
            "instruction": (
                "Vérifier manuellement Safe Harbor, autorisation d'automatisation, "
                "assets in-scope/out-of-scope, exclusions, comptes de test et limite de requêtes."
            ),
        },
        {
            "id": "activate_scanner",
            "title": "Ouvrir les verrous de scan réel",
            "when": "activation",
            "done": required_ok,
            "instruction": (
                "Seulement après la revue du programme : activer les scans, désactiver "
                "DRY_RUN, activer Nuclei et le worker scanner dédié, puis revérifier le pré-vol."
            ),
        },
        {
            "id": "launch_confirmed_preview",
            "title": "Lancer uniquement une preview confirmée",
            "when": "activation",
            "done": False,
            "instruction": (
                "Prévisualiser les règles exécutables, vérifier une dernière fois le scope, "
                "cocher la confirmation humaine, puis lancer la campagne."
            ),
        },
    ]

    return {
        "status": "ready" if required_ok else "blocked",
        "program_review_ready": program_review_ready,
        "live_scan_ready": required_ok,
        "checks": checks,
        "scanner_block_reasons": list(scanner.get("dispatch_block_reasons") or []),
        "deployment_status": deployment.get("status"),
        "submission_enabled": submission_enabled if submission_valid else False,
        "report_sync_enabled": report_sync_enabled if report_sync_valid else False,
        "read_only": True,
        "contains_secrets": False,
        "operator_steps": operator_steps,
        "activation_template": [
            "XBOW_ENABLE_ACTIVE_SCANS=true",
            "DRY_RUN=false",
            "XBOW_ENABLE_NUCLEI=true",
            "XBOW_NUCLEI_ALLOWED_VERSION=3.11.1",
            "XBOW_SCANNER_ALLOWED_ENGINES=nuclei",
            "XBOW_SCANNER_SANDBOX_PROFILE=restricted-v1",
        ],
        "scanner_start_command": "docker compose --profile scanner up -d --build",
        "next_operator_step": (
            "Sélectionner un programme HackerOne, relire sa policy et confirmer "
            "Safe Harbor, automation, scope et limite de requêtes."
            if required_ok
            else "Résoudre les checks obligatoires en échec avant tout scan réel."
        ),
    }
