# Repo Brain

- Index mode: incremental
- Files indexed: 391
- Files reparsed this run: 5
- Symbols: 3739
- Internal import edges: 1278
- Impacted files: 16
- Selected tests: 13

## Languages
- python: 387 files
- javascript: 4 files

## Highest-density symbol files
- frontend/hackerone.js: 126 symbols
- backend/app/main.py: 93 symbols
- backend/tests/test_openapi_testgen.py: 71 symbols
- backend/app/hackerone_api.py: 62 symbols
- backend/tests/test_frontend_auth_proxy.py: 48 symbols
- frontend/simple.js: 48 symbols
- backend/app/storage_core.py: 44 symbols
- backend/tests/test_recon_worker.py: 41 symbols
- backend/tests/test_storage.py: 38 symbols
- backend/app/recon_worker.py: 33 symbols
- backend/tests/test_htb_lab.py: 33 symbols
- backend/app/storage_backend.py: 32 symbols
- backend/tests/test_auth.py: 32 symbols
- backend/tests/test_browser.py: 32 symbols
- backend/tests/test_jobqueue.py: 32 symbols
- backend/app/redis_jobqueue.py: 27 symbols
- backend/tests/test_pentagi_worker_service.py: 27 symbols
- backend/app/hackerone_client.py: 26 symbols
- backend/app/jobqueue.py: 26 symbols
- backend/tests/test_orchestrator.py: 26 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 5
- outline files retained: 389
- top-level items retained: 5072
- direct members retained: 1113
- symbol shards: 26
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

