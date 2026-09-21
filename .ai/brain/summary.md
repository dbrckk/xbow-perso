# Repo Brain

- Index mode: incremental
- Files indexed: 360
- Files reparsed this run: 8
- Symbols: 3167
- Internal import edges: 1205
- Impacted files: 23
- Selected tests: 30

## Languages
- python: 357 files
- javascript: 3 files

## Highest-density symbol files
- frontend/hackerone.js: 126 symbols
- backend/app/main.py: 89 symbols
- backend/app/hackerone_api.py: 46 symbols
- backend/app/storage_core.py: 43 symbols
- backend/tests/test_storage.py: 38 symbols
- backend/tests/test_recon_worker.py: 36 symbols
- backend/tests/test_browser.py: 32 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/app/storage_backend.py: 30 symbols
- backend/app/recon_worker.py: 29 symbols
- backend/app/redis_jobqueue.py: 27 symbols
- backend/tests/test_pentagi_worker_service.py: 27 symbols
- backend/app/jobqueue.py: 26 symbols
- backend/tests/test_auth.py: 26 symbols
- backend/tests/test_pentagi_transport.py: 26 symbols
- backend/app/hackerone_client.py: 25 symbols
- backend/tests/test_orchestrator.py: 25 symbols
- backend/app/worker_service.py: 24 symbols
- backend/tests/test_distributed_concurrency.py: 24 symbols
- backend/tests/test_validator.py: 24 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 8
- outline files retained: 359
- top-level items retained: 4460
- direct members retained: 1035
- symbol shards: 25
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

