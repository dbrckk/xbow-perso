# Repo Brain

- Index mode: incremental
- Files indexed: 328
- Files reparsed this run: 8
- Symbols: 2991
- Internal import edges: 1131
- Impacted files: 166
- Selected tests: 114

## Languages
- python: 325 files
- javascript: 3 files

## Highest-density symbol files
- frontend/hackerone.js: 120 symbols
- backend/app/main.py: 89 symbols
- backend/app/storage_core.py: 40 symbols
- backend/app/hackerone_api.py: 39 symbols
- backend/tests/test_storage.py: 38 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/tests/test_browser.py: 28 symbols
- backend/tests/test_recon_worker.py: 28 symbols
- backend/app/redis_jobqueue.py: 27 symbols
- backend/app/storage_backend.py: 27 symbols
- backend/tests/test_pentagi_worker_service.py: 27 symbols
- backend/app/jobqueue.py: 26 symbols
- backend/tests/test_auth.py: 26 symbols
- backend/tests/test_pentagi_transport.py: 26 symbols
- backend/app/hackerone_client.py: 25 symbols
- backend/tests/test_orchestrator.py: 25 symbols
- backend/app/worker_service.py: 24 symbols
- backend/tests/test_distributed_concurrency.py: 24 symbols
- backend/tests/test_validator.py: 24 symbols
- backend/app/production_migration.py: 22 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 8
- outline files retained: 327
- top-level items retained: 4192
- direct members retained: 993
- symbol shards: 25
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

