# Change impact

Base: 1d8671445ba25243a9d5af647b0db3e3ccbc05f2
Head: 86d8b3df43349d5b84f4034afa5ae3aaf0e45a43

## Changed files
- M .env.example
- M README.md
- M backend/app/hackerone_api.py
- A backend/app/hackerone_catalog.py
- M backend/app/postgres_storage.py
- M backend/app/storage_backend.py
- M backend/app/storage_core.py
- M backend/app/worker_service.py
- A backend/tests/test_hackerone_catalog.py
- M backend/tests/test_hackerone_control_center_api.py
- M docker-compose.yml
- M frontend/app.css
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
