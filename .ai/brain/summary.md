# Repo Brain

- Index mode: incremental
- Files indexed: 316
- Files reparsed this run: 5
- Symbols: 2800
- Internal import edges: 1094
- Impacted files: 149
- Selected tests: 95

## Languages
- python: 313 files
- javascript: 3 files

## Highest-density symbol files
- frontend/hackerone.js: 90 symbols
- backend/app/main.py: 88 symbols
- backend/tests/test_storage.py: 37 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/app/storage_core.py: 30 symbols
- backend/app/hackerone_api.py: 29 symbols
- backend/tests/test_browser.py: 28 symbols
- backend/tests/test_recon_worker.py: 28 symbols
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
- AST files reparsed this run: 5
- outline files retained: 315
- top-level items retained: 3981
- direct members retained: 953
- symbol shards: 25
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

