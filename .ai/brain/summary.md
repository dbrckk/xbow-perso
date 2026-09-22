# Repo Brain

- Index mode: incremental
- Files indexed: 372
- Files reparsed this run: 8
- Symbols: 3296
- Internal import edges: 1217
- Impacted files: 163
- Selected tests: 110

## Languages
- python: 368 files
- javascript: 4 files

## Highest-density symbol files
- frontend/hackerone.js: 126 symbols
- backend/app/main.py: 90 symbols
- backend/app/hackerone_api.py: 53 symbols
- backend/app/storage_core.py: 44 symbols
- backend/tests/test_storage.py: 38 symbols
- backend/tests/test_recon_worker.py: 36 symbols
- backend/app/storage_backend.py: 32 symbols
- backend/tests/test_auth.py: 32 symbols
- backend/tests/test_browser.py: 32 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/app/recon_worker.py: 29 symbols
- backend/app/redis_jobqueue.py: 27 symbols
- backend/tests/test_pentagi_worker_service.py: 27 symbols
- backend/app/jobqueue.py: 26 symbols
- backend/tests/test_pentagi_transport.py: 26 symbols
- backend/app/hackerone_client.py: 25 symbols
- backend/tests/test_orchestrator.py: 25 symbols
- backend/app/worker_service.py: 24 symbols
- backend/tests/test_validator.py: 24 symbols
- backend/app/browser.py: 22 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 8
- outline files retained: 370
- top-level items retained: 4575
- direct members retained: 1049
- symbol shards: 25
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

