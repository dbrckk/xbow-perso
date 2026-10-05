from pathlib import Path


def test_frontend_smoke_test_avoids_pipefail_broken_pipe():
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert (
        "curl -fsS http://127.0.0.1:8080/ | grep -q "
        not in workflow
    )
    assert (
        'html="$(curl -fsS http://127.0.0.1:8080/)"'
        in workflow
    )
    assert (
        "grep -q 'class="app-shell simple-shell"' <<< "$html""
        in workflow
    )
