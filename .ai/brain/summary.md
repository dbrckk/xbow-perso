# Repo Brain

- Index mode: incremental
- Files indexed: 489
- Files reparsed this run: 2
- Symbols: 5140
- Internal import edges: 1528
- Impacted files: 11
- Selected tests: 3

## Languages
- python: 485 files
- javascript: 4 files

## Highest-density symbol files
- frontend/hackerone.js: 126 symbols
- backend/tests/test_no_finding_recovery.py: 124 symbols
- backend/app/main.py: 91 symbols
- backend/tests/test_openapi_testgen.py: 71 symbols
- backend/tests/test_coverage.py: 63 symbols
- backend/app/hackerone_api.py: 62 symbols
- backend/tests/test_frontend_auth_proxy.py: 50 symbols
- frontend/simple.js: 50 symbols
- backend/tests/test_strix_runner_rpc.py: 46 symbols
- backend/tests/test_recon_worker.py: 45 symbols
- backend/app/storage_core.py: 44 symbols
- backend/tests/test_technology_fingerprint_intelligence.py: 41 symbols
- backend/tests/test_storage.py: 38 symbols
- backend/app/strix_runner_rpc.py: 35 symbols
- backend/tests/test_strix_egress_transport.py: 35 symbols
- backend/app/recon_worker.py: 34 symbols
- backend/tests/test_htb_lab.py: 34 symbols
- backend/tests/test_finding_intelligence.py: 33 symbols
- backend/tests/test_jobqueue.py: 33 symbols
- backend/tests/test_runtime_capabilities.py: 33 symbols

## Agent routing
- Read impact.json first after project/change context.
- Use selected-tests.json before broad validation.
- Search lookup.json for symbol routing; ast-grep enrichment may provide exact ranges.
- Verify source before editing.

## ast-grep enrichment
- ast-grep outline: available
- AST index mode: incremental
- AST files reparsed this run: 2
- outline files retained: 487
- top-level items retained: 6946
- direct members retained: 1791
- symbol shards: 26
- route named symbols via ast-routing.json, then fetch one ast-symbols/<initial>.json shard

