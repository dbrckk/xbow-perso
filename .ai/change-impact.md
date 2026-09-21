# Change impact

Base: 906fe961e6e1dc3d41f008da586ee54da77fa762
Head: 53e059b524937bf85cabb459d50917192ef9716e

## Changed files
- M .env.example
- M backend/Dockerfile
- M backend/app/browser.py
- A backend/app/high_value_intelligence.py
- A backend/app/identity_access.py
- M backend/app/main.py
- M backend/app/orchestrator.py
- M backend/app/recon_worker.py
- M backend/app/runtime_capabilities.py
- M backend/app/worker_service.py
- M backend/tests/test_browser.py
- A backend/tests/test_high_value_intelligence.py
- A backend/tests/test_identity_access.py
- M backend/tests/test_recon_worker.py
- M backend/tests/test_runtime_capabilities.py
- M backend/tests/test_scanner_runtime_contract.py
- M docker-compose.yml

## Affected areas
- (root)
- backend

## Related test candidates
- No direct filename-based test match detected.

## Agent guidance
- Read this file before broad repository exploration.
- Inspect only the affected areas first.
- Use .ai/commands.json to choose validation commands.
- Expand scope only if the change crosses module boundaries or tests fail.
