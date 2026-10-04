# Repo Brain

- Index mode: incremental
- Files indexed: 411
- Files reparsed this run: 2
- Symbols: 3996
- Internal import edges: 1339
- Impacted files: 2
- Selected tests: 1

## Languages
- python: 407 files
- javascript: 4 files

## Highest-density symbol files
- frontend/hackerone.js: 126 symbols
- backend/app/main.py: 93 symbols
- backend/tests/test_openapi_testgen.py: 71 symbols
- backend/app/hackerone_api.py: 62 symbols
- backend/tests/test_frontend_auth_proxy.py: 50 symbols
- frontend/simple.js: 50 symbols
- backend/tests/test_recon_worker.py: 45 symbols
- backend/app/storage_core.py: 44 symbols
- backend/tests/test_storage.py: 38 symbols
- backend/tests/test_strix_egress_transport.py: 35 symbols
- backend/app/recon_worker.py: 34 symbols
- backend/tests/test_htb_lab.py: 34 symbols
- backend/tests/test_jobqueue.py: 33 symbols
- backend/app/storage_backend.py: 32 symbols
- backend/tests/test_auth.py: 32 symbols
- backend/tests/test_browser.py: 32 symbols
- backend/app/redis_jobqueue.py: 28 symbols
- backend/tests/test_redis_jobqueue.py: 28 symbols
- backend/app/jobqueue.py: 27 symbols
- backend/tests/test_pentagi_worker_service.py: 27 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 2
- outline files retained: 409
- top-level items retained: 5415
- direct members retained: 1233
- symbol shards: 26
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

