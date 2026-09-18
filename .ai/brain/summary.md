# Repo Brain

- Index mode: full
- Files indexed: 282
- Files reparsed this run: 282
- Symbols: 2389
- Internal import edges: 566
- Impacted files: 0
- Selected tests: 0

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
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- outline files: 281
- top-level items: 3522
- direct members: 847
- symbol shards: 25
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

