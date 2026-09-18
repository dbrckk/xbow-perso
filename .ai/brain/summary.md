# Repo Brain

- Files indexed: 282
- Symbols: 2389
- Internal import edges: 566

## Languages
- python: 279 files
- javascript: 3 files

## Highest-density symbol files
- backend/app/main.py: 82 symbols
- backend/tests/test_storage.py: 36 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/app/storage.py: 30 symbols
- backend/tests/test_browser.py: 28 symbols
- backend/tests/test_recon_worker.py: 28 symbols
- backend/app/redis_jobqueue.py: 27 symbols
- backend/app/jobqueue.py: 26 symbols
- backend/tests/test_auth.py: 26 symbols
- backend/tests/test_pentagi_transport.py: 26 symbols
- backend/tests/test_pentagi_worker_service.py: 26 symbols
- backend/tests/test_orchestrator.py: 25 symbols
- backend/app/worker_service.py: 24 symbols
- backend/tests/test_distributed_concurrency.py: 24 symbols
- backend/tests/test_validator.py: 24 symbols
- backend/app/browser.py: 21 symbols
- backend/tests/test_api_rate_limit.py: 21 symbols
- backend/tests/test_queue_age_metrics.py: 21 symbols
- backend/app/recon_worker.py: 19 symbols
- backend/app/storage_backend.py: 19 symbols

## Agent routing
- Search lookup.json first for direct symbol-to-file routing.
- Use symbols.json only when broader symbol metadata is needed.
- Use code-graph.json to inspect likely internal import relationships.
- Use imports.json when a changed file crosses module boundaries.
- Treat graph edges as static hints; verify source before editing.
