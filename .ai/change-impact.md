# Change impact

Base: 1519a9b32b352469edc572cae7490f146909f3f5
Head: 14fecdb2744fb710b46af28186b691b00dbf2d0f

## Changed files
- M .env.example
- M README.md
- M backend/app/hackerone_api.py
- A backend/app/hackerone_report_sync_worker.py
- A backend/app/hackerone_report_tracking.py
- M backend/app/storage_backend.py
- M backend/app/storage_core.py
- M backend/tests/test_deployment_config.py
- M backend/tests/test_frontend_policy_launcher.py
- A backend/tests/test_hackerone_report_sync_worker.py
- M backend/tests/test_storage.py
- M docker-compose.distributed.yml
- M docker-compose.yml
- M frontend/hackerone.js
- M frontend/index.html
- M frontend/sw.js

## Affected areas
- (root)
- backend
- frontend

## Related test candidates
- No direct filename-based test match detected.

## Agent guidance
- Read this file before broad repository exploration.
- Inspect only the affected areas first.
- Use .ai/commands.json to choose validation commands.
- Expand scope only if the change crosses module boundaries or tests fail.
