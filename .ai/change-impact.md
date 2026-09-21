# Change impact

Base: e333ff6b40fcca27eaf9fb7c1beef54cf44d3720
Head: 34203501338b332e0519cb7606146470d93d7e39

## Changed files
- M backend/app/hackerone_api.py
- M backend/app/hackerone_batch.py
- M backend/app/main.py
- M backend/app/storage_backend.py
- M backend/app/storage_core.py
- M backend/tests/test_hackerone_batch.py
- M backend/tests/test_hackerone_batch_api.py
- M backend/tests/test_hackerone_prelaunch.py
- M backend/tests/test_hackerone_reviewed_batch_api.py
- M backend/tests/test_live_activation_profile.py
- A docs/RELEASE_0.5.1.md
- M frontend/hackerone.js
- M frontend/sw.js
- M scripts/mobile-production-update.sh

## Affected areas
- backend
- docs
- frontend
- scripts

## Related test candidates
- No direct filename-based test match detected.

## Agent guidance
- Read this file before broad repository exploration.
- Inspect only the affected areas first.
- Use .ai/commands.json to choose validation commands.
- Expand scope only if the change crosses module boundaries or tests fail.
