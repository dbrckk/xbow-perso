# Change impact

Base: 7f0a2ead28daba495c2239b8ad796bf34e965d22
Head: 52917ab83a52c6a6ad95b5746705e0d03cebeffd

## Changed files
- M .env.example
- M .github/workflows/ci.yml
- M README.md
- M backend/app/runtime_capabilities.py
- M backend/app/strix_broker.py
- A backend/app/strix_broker_client.py
- A backend/app/strix_broker_models.py
- A backend/app/strix_egress.py
- A backend/app/strix_egress_transport.py
- M backend/tests/test_runtime_capabilities.py
- M backend/tests/test_strix_broker.py
- A backend/tests/test_strix_broker_client.py
- M backend/tests/test_strix_broker_runtime.py
- A backend/tests/test_strix_egress.py
- A backend/tests/test_strix_egress_transport.py
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
