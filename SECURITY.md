# Security Policy

## Scope

xbow-perso is an orchestration platform for **authorized** bug-bounty and security testing. Security reports about xbow-perso itself are welcome. Do not use a security report as authorization to test third-party systems.

## Reporting a vulnerability

Do **not** open a public GitHub issue for a suspected vulnerability, exposed credential, authentication bypass, or other security-sensitive defect.

Use GitHub's private vulnerability reporting feature for this repository when it is available. Include:

- affected version, commit, or deployment mode;
- affected component and configuration;
- minimal reproduction steps;
- expected and observed behavior;
- impact assessment;
- relevant logs with credentials, tokens, cookies, and personal data removed.

Do not include live third-party credentials, exploit data from systems you do not own, or destructive proof-of-concept material.

## Safe research expectations

When assessing xbow-perso:

- use systems and accounts you own or are explicitly authorized to test;
- keep testing non-destructive;
- do not perform denial-of-service, social engineering, credential attacks, or persistence;
- stop if testing could affect another tenant, user, or third-party service;
- preserve evidence without collecting unrelated sensitive data.

## Secrets

Never commit API keys, passwords, session cookies, private keys, vault contents, database dumps, Redis snapshots, or populated environment files. Rotate a secret immediately if it is accidentally committed or exposed.

## Supported versions

Security fixes target the current default branch. Older commits and deployments should be upgraded before reporting behavior that has already been fixed on the default branch.

## Security design

Runtime safety is intentionally fail-closed. Scope authorization, worker admission, scanner sandboxing, independent validation, evidence handling, and audit controls are security boundaries. Changes that weaken those boundaries require explicit review and tests.
