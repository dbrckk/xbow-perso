# Repo Brain

- Index mode: incremental
- Files indexed: 301
- Files reparsed this run: 11
- Symbols: 2612
- Internal import edges: 1052
- Impacted files: 27
- Selected tests: 22

## Languages
- python: 298 files
- javascript: 3 files

## Highest-density symbol files
- backend/app/main.py: 85 symbols
- backend/tests/test_storage.py: 37 symbols
- frontend/hackerone.js: 37 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/app/storage_core.py: 30 symbols
- backend/tests/test_browser.py: 28 symbols
- backend/tests/test_recon_worker.py: 28 symbols
- backend/app/redis_jobqueue.py: 27 symbols
- backend/tests/test_pentagi_worker_service.py: 27 symbols
- backend/app/hackerone_api.py: 26 symbols
- backend/app/jobqueue.py: 26 symbols
- backend/tests/test_auth.py: 26 symbols
- backend/tests/test_pentagi_transport.py: 26 symbols
- backend/app/hackerone_client.py: 25 symbols
- backend/tests/test_orchestrator.py: 25 symbols
- backend/app/worker_service.py: 24 symbols
- backend/tests/test_distributed_concurrency.py: 24 symbols
- backend/tests/test_validator.py: 24 symbols
- backend/app/browser.py: 21 symbols
- backend/app/storage_backend.py: 21 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 11
- outline files retained: 300
- top-level items retained: 3801
- direct members retained: 906
- symbol shards: 25
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

