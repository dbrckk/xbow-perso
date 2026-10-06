from types import SimpleNamespace

import pytest

from app.version_ambiguity import (
    VERSION_AMBIGUITY_SCHEMA,
    analyze_version_ambiguity,
)


def _finding(*, cpe=None):
    return SimpleNamespace(cpe=list(cpe or []))


def _fp(product, version, confidence):
    return SimpleNamespace(
        normalized_product=product,
        version=version,
        confidence=confidence,
    )


def test_conflicting_versions_for_same_product_are_ambiguous():
    result = analyze_version_ambiguity(
        _finding(),
        [
            _fp("nginx", "1.24.0", 0.9),
            _fp("nginx", "1.25.1", 0.9),
        ],
    )

    assert result.schema == VERSION_AMBIGUITY_SCHEMA
    assert result.ambiguous is True
    assert "conflicting_version_fingerprints" in result.reasons
    assert result.conflicting_product_count == 1


def test_single_high_confidence_version_is_not_ambiguous():
    result = analyze_version_ambiguity(
        _finding(),
        [_fp("nginx", "1.24.0", 0.9)],
    )

    assert result.ambiguous is False
    assert result.reasons == ()
    assert result.high_confidence_versioned_count == 1


def test_only_low_confidence_versions_are_ambiguous():
    result = analyze_version_ambiguity(
        _finding(),
        [_fp("nginx", "1.24.0", 0.6)],
    )

    assert result.ambiguous is True
    assert "low_confidence_version_fingerprints" in result.reasons


def test_wildcard_cpe_is_ambiguous_even_with_high_confidence_banner():
    result = analyze_version_ambiguity(
        _finding(
            cpe=["cpe:2.3:a:vendor:product:*:*:*:*:*:*:*:*"]
        ),
        [_fp("product", "1.2.3", 0.9)],
    )

    assert result.ambiguous is True
    assert "wildcard_cpe_version" in result.reasons
    assert result.wildcard_cpe_count == 1


def test_cpe_without_versioned_fingerprint_is_ambiguous():
    result = analyze_version_ambiguity(
        _finding(
            cpe=["cpe:2.3:a:vendor:product:1.2.3:*:*:*:*:*:*:*"]
        ),
        [],
    )

    assert result.ambiguous is True
    assert "no_versioned_fingerprint" in result.reasons


def test_distinct_products_with_distinct_versions_are_not_conflicting():
    result = analyze_version_ambiguity(
        _finding(),
        [
            _fp("nginx", "1.24.0", 0.9),
            _fp("openssl", "3.0.12", 0.9),
        ],
    )

    assert result.conflicting_product_count == 0
    assert result.ambiguous is False


@pytest.mark.parametrize("threshold", (0.49, 1.01))
def test_invalid_confidence_threshold_fails_closed(threshold):
    with pytest.raises(ValueError, match="between 0.5 and 1.0"):
        analyze_version_ambiguity(
            _finding(),
            [_fp("nginx", "1.24.0", 0.9)],
            high_confidence_threshold=threshold,
        )
