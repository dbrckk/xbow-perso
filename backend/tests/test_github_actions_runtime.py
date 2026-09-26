from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
    ".github/workflows/supply-chain.yml",
    ".github/workflows/mobile-vps-deploy.yml",
    ".github/workflows/release-images.yml",
    ".github/workflows/release-quality-gate.yml",
)


def test_core_github_actions_use_node24_capable_major_versions():
    combined = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in WORKFLOWS
    )

    assert "actions/checkout@v4" not in combined
    assert "actions/setup-python@v5" not in combined
    assert "actions/setup-node@v4" not in combined
    assert "actions/checkout@v7" in combined
    assert "actions/setup-python@v7" in combined
    assert "actions/setup-node@v7" in combined
