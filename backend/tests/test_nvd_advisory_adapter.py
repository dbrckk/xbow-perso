import pytest

from app.nvd_advisory_adapter import (
    NVD_ADVISORY_ADAPTER_SCHEMA,
    NvdAdvisoryAdapterError,
    adapt_nvd_cve_api_v2,
)


def _wrapper(*matches, cve_id="CVE-2026-12345", operator="OR", negate=False):
    return {
        "cve": {
            "id": cve_id,
            "configurations": [
                {
                    "nodes": [
                        {
                            "operator": operator,
                            "negate": negate,
                            "cpeMatch": list(matches),
                        }
                    ]
                }
            ],
        }
    }


def _match(
    *,
    criteria="cpe:2.3:a:djangoproject:django:*:*:*:*:*:*:*:*",
    vulnerable=True,
    **bounds,
):
    return {
        "vulnerable": vulnerable,
        "criteria": criteria,
        **bounds,
    }


def test_nvd_bounded_range_is_converted_to_internal_expression():
    result = adapt_nvd_cve_api_v2(
        {
            "vulnerabilities": [
                _wrapper(
                    _match(
                        versionStartIncluding="5.0",
                        versionEndExcluding="5.2.0",
                    )
                )
            ]
        }
    )

    assert result.schema == NVD_ADVISORY_ADAPTER_SCHEMA
    assert result.input_vulnerability_count == 1
    assert result.output_entry_count == 1
    assert result.document == {
        "count": 1,
        "entries": [
            {
                "cve_id": "CVE-2026-12345",
                "vendor": "djangoproject",
                "product": "django",
                "affected_version_ranges": [">=5.0,<5.2.0"],
            }
        ],
    }


def test_nvd_exact_numeric_cpe_version_becomes_exact_range():
    result = adapt_nvd_cve_api_v2(
        {
            "vulnerabilities": [
                _wrapper(
                    _match(
                        criteria=(
                            "cpe:2.3:a:vendor:product:1.2.3:"
                            "*:*:*:*:*:*:*"
                        )
                    )
                )
            ]
        }
    )

    assert result.document["entries"][0]["affected_version_ranges"] == [
        "=1.2.3"
    ]


def test_nvd_merges_ranges_for_same_cve_vendor_product():
    result = adapt_nvd_cve_api_v2(
        {
            "vulnerabilities": [
                _wrapper(
                    _match(versionEndExcluding="4.2.16"),
                    _match(
                        versionStartIncluding="5.0",
                        versionEndExcluding="5.1.3",
                    ),
                )
            ]
        }
    )

    assert result.output_entry_count == 1
    assert result.document["entries"][0]["affected_version_ranges"] == [
        "<4.2.16",
        ">=5.0,<5.1.3",
    ]


def test_non_vulnerable_match_is_not_converted():
    result = adapt_nvd_cve_api_v2(
        {
            "vulnerabilities": [
                _wrapper(
                    _match(vulnerable=False, versionEndExcluding="5.2.0")
                )
            ]
        }
    )

    assert result.output_entry_count == 0
    assert result.skipped_non_vulnerable_matches == 1


def test_unbounded_wildcard_version_is_not_guessed():
    result = adapt_nvd_cve_api_v2(
        {"vulnerabilities": [_wrapper(_match())]}
    )

    assert result.output_entry_count == 0
    assert result.skipped_unusable_version_matches == 1


@pytest.mark.parametrize(
    "operator,negate",
    (("AND", False), ("OR", True)),
)
def test_complex_logical_configuration_is_skipped(operator, negate):
    result = adapt_nvd_cve_api_v2(
        {
            "vulnerabilities": [
                _wrapper(
                    _match(versionEndExcluding="5.2.0"),
                    operator=operator,
                    negate=negate,
                )
            ]
        }
    )

    assert result.output_entry_count == 0
    assert result.skipped_complex_configurations == 1


def test_child_node_configuration_is_skipped():
    document = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-12345",
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "operator": "OR",
                                    "cpeMatch": [],
                                    "children": [
                                        {
                                            "operator": "OR",
                                            "cpeMatch": [
                                                _match(
                                                    versionEndExcluding="5.2.0"
                                                )
                                            ],
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            }
        ]
    }

    result = adapt_nvd_cve_api_v2(document)

    assert result.output_entry_count == 0
    assert result.skipped_complex_configurations == 1


def test_non_numeric_nvd_bound_is_kept_unknown():
    result = adapt_nvd_cve_api_v2(
        {
            "vulnerabilities": [
                _wrapper(
                    _match(
                        versionStartIncluding="5.1.2-custom",
                        versionEndExcluding="5.2.0",
                    )
                )
            ]
        }
    )

    assert result.output_entry_count == 0
    assert result.skipped_unusable_version_matches == 1


def test_invalid_cve_identifier_is_rejected():
    with pytest.raises(NvdAdvisoryAdapterError, match="CVE id"):
        adapt_nvd_cve_api_v2(
            {
                "vulnerabilities": [
                    _wrapper(
                        _match(versionEndExcluding="5.2.0"),
                        cve_id="CVE-invalid",
                    )
                ]
            }
        )
