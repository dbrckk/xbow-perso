# Change impact

Base: f040a64f4d7c28a8be43488819530ed30769ca36
Head: dfc71dec65811722648cad96b72e4c63c2f20c67

## Changed files
- M .github/workflows/ci.yml
- A backend/Dockerfile.scanner
- A backend/app/pentagi_action_gateway.py
- M backend/app/pentagi_adapter.py
- M backend/app/pentagi_worker_service.py
- M backend/app/storage.py
- M backend/app/storage_backend.py
- A backend/app/storage_core.py
- M backend/app/worker.py
- M backend/tests/test_nuclei_worker_plan.py
- A backend/tests/test_pentagi_action_gateway.py
- M backend/tests/test_pentagi_adapter.py
- M backend/tests/test_pentagi_worker_service.py
- A backend/tests/test_scanner_runtime_contract.py
- M docker-compose.yml
- A docs/superpowers/plans/2026-09-16-nuclei-pentagi-controlled-runtime.md
- A docs/superpowers/specs/2026-09-16-nuclei-pentagi-controlled-runtime-design.md

## Affected areas
- .github
- backend
- (root)
- docs

## Related test candidates
- No direct filename-based test match detected.

## Agent guidance
- Read this file before broad repository exploration.
- Inspect only the affected areas first.
- Use .ai/commands.json to choose validation commands.
- Expand scope only if the change crosses module boundaries or tests fail.
