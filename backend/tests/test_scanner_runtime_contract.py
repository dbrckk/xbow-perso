from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_scanner_worker_uses_dedicated_pinned_nuclei_image():
    compose = (ROOT / "docker-compose.yml").read_text()
    scanner = compose.split("  scanner-worker:", 1)[1].split("\n  pentagi-worker:", 1)[0]
    assert "context: ./backend" in scanner
    assert "dockerfile: Dockerfile.scanner" in scanner
    assert "XBOW_NUCLEI_ALLOWED_VERSION: ${XBOW_NUCLEI_ALLOWED_VERSION:-3.11.1}" in scanner


def test_scanner_dockerfile_verifies_pinned_nuclei_and_templates():
    dockerfile = (ROOT / "backend" / "Dockerfile.scanner").read_text()
    assert "NUCLEI_VERSION=3.11.1" in dockerfile
    assert "NUCLEI_TEMPLATES_VERSION=10.4.8" in dockerfile
    assert "NUCLEI_TEMPLATES_COMMIT=e5f19e6144135e107962bb943231413796fd7fe7" in dockerfile
    assert "sha256sum -c" in dockerfile
    assert "nuclei -version" in dockerfile
    assert "git rev-parse HEAD" in dockerfile
    assert "nuclei-templates-v10.4.8" in dockerfile


def test_ci_builds_the_scanner_profile_image():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "docker compose --profile scanner build --pull scanner-worker" in workflow



def test_general_worker_image_verifies_pinned_recon_toolchain():
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
    assert "KATANA_VERSION=1.7.0" in dockerfile
    assert "HTTPX_VERSION=1.12.0" in dockerfile
    assert "SUBFINDER_VERSION=2.16.0" in dockerfile
    assert "sha256sum -c -" in dockerfile
    assert '"/usr/local/bin/$tool" -version' in dockerfile


def test_compose_wires_recon_flags_to_general_worker():
    compose = (ROOT / "docker-compose.yml").read_text()
    worker = compose.split("  worker:", 1)[1].split("\n  scanner-worker:", 1)[0]
    assert "XBOW_ENABLE_RECON: ${XBOW_ENABLE_RECON:-false}" in worker
    assert "XBOW_ENABLE_EXTERNAL_RECON: ${XBOW_ENABLE_EXTERNAL_RECON:-false}" in worker
    assert "XBOW_EXTERNAL_RECON_MAX_OUTPUT_BYTES:" in worker
