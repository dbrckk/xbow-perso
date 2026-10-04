# Change impact

Base: 81b1730f9baba0ea229c4527c6252f6b8a1b6cd7
Head: 0120d731db2a27ed822b3aedaeb89ef8ffbbf8fc

## Changed files
- M .env.example
- M .github/workflows/ci.yml
- M README.md
- M backend/Dockerfile.strix-runner
- M backend/app/runtime_capabilities.py
- M backend/app/strix_runner_attestation.py
- A backend/app/strix_runner_rpc.py
- M backend/tests/test_runtime_capabilities.py
- M backend/tests/test_strix_runner_attestation.py
- A backend/tests/test_strix_runner_rpc.py
- M docker-compose.yml

## Affected areas
- (root)
- .github
- backend

## Related test candidates
- No direct filename-based test match detected.

## Agent guidance
- Read this file before broad repository exploration.
- Inspect only the affected areas first.
- Use .ai/commands.json to choose validation commands.
- Expand scope only if the change crosses module boundaries or tests fail.
