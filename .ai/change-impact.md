# Change impact

Base: ac41df2b97e8da523141e28ecf8bb34186898ca6
Head: a9be68eac17912af108a8cdce64a7181f29cc5da

## Changed files
- M .env.example
- M README.md
- M backend/app/hackerone_api.py
- M backend/app/hackerone_binding.py
- A backend/app/hackerone_client.py
- M backend/tests/test_frontend_policy_launcher.py
- A backend/tests/test_hackerone_client.py
- A backend/tests/test_hackerone_control_center_api.py
- A backend/tests/test_hackerone_remote_binding.py
- A backend/tests/test_hackerone_remote_snapshot.py
- A docs/superpowers/plans/2026-09-17-hackerone-control-center.md
- A docs/superpowers/specs/2026-09-17-hackerone-control-center-design.md
- M frontend/app.css
- M frontend/hackerone.js
- M frontend/index.html
- M frontend/sw.js

## Affected areas
- (root)
- backend
- docs
- frontend

## Related test candidates
- No direct filename-based test match detected.

## Agent guidance
- Read this file before broad repository exploration.
- Inspect only the affected areas first.
- Use .ai/commands.json to choose validation commands.
- Expand scope only if the change crosses module boundaries or tests fail.
