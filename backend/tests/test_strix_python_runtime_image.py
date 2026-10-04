from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_python_runtime_image_is_pinned_and_inert():
    dockerfile = (
        ROOT / "backend" / "Dockerfile.strix-python-runtime"
    ).read_text()

    assert "python:3.12.14-slim@sha256:" in dockerfile
    assert "UV_VERSION=0.12.10" in dockerfile
    assert (
        "173d95a0c32d18c896c46ba6fafbf3cf9c14ab74b033f81b76c883ef492a976b"
        in dockerfile
    )
    assert (
        "9ff6b9d4665edcdd3a88dcc73cd1eb641754deb927f14e8c62ebfde6bf4f5f5e"
        in dockerfile
    )
    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert (
        "1a93fbf0f18fad6bf4802c41fa5e032ce50880a655fddee47f6bec4f1ea2155b"
        in dockerfile
    )
    assert (
        "b2939f8c6339817a2abeff2ba266838af3d45e4e05593fe89db11464c8e7a0d4"
        in dockerfile
    )
    assert "COPY app/strix_backend_hook.py" in dockerfile
    assert "COPY app/strix_python_compat_probe.py" in dockerfile
    assert "app.strix_backend_hook --self-test" in dockerfile
    assert "app.strix_python_compat_probe --self-test" in dockerfile
    assert "XBOW_STRIX_ACTIVE_EXECUTION=false" in dockerfile
    assert "docker.sock" not in dockerfile


def test_python_runtime_image_does_not_expose_scan_entrypoint():
    dockerfile = (
        ROOT / "backend" / "Dockerfile.strix-python-runtime"
    ).read_text()

    assert "strix.interface.main" not in dockerfile
    assert "--target" not in dockerfile
    assert "--serve" not in dockerfile
    assert 'CMD ["/opt/strix-python/.venv/bin/python"' in dockerfile
    assert '"app.strix_backend_hook"' in dockerfile
    assert '"--self-test"' in dockerfile


def test_ci_builds_and_self_tests_inert_python_runtime():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "Dockerfile.strix-python-runtime" in workflow
    assert "xbow-strix-python-runtime:ci" in workflow
    assert "--network none" in workflow
