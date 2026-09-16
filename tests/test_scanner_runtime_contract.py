from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_scanner_worker_uses_dedicated_pinned_nuclei_image():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    scanner = compose["services"]["scanner-worker"]
    assert scanner["build"]["context"] == "./backend"
    assert scanner["build"]["dockerfile"] == "Dockerfile.scanner"
    assert scanner["environment"]["XBOW_NUCLEI_ALLOWED_VERSION"] == "${XBOW_NUCLEI_ALLOWED_VERSION:-3.11.1}"


def test_scanner_dockerfile_verifies_pinned_nuclei_and_templates():
    dockerfile = (ROOT / "backend" / "Dockerfile.scanner").read_text()
    assert "NUCLEI_VERSION=3.11.1" in dockerfile
    assert "NUCLEI_TEMPLATES_VERSION=10.4.8" in dockerfile
    assert "sha256sum -c" in dockerfile
    assert "nuclei -version" in dockerfile
    assert "nuclei-templates-v10.4.8" in dockerfile
