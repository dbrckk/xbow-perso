from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .affected_version_range import build_affected_version_range_evidence
from .cve_advisory_catalog import (
    CveAdvisoryCatalog,
    CveAdvisoryEntry,
    find_verified_cve_advisories,
)
from .vulnerability_intelligence import finding_cve_ids


CVE_ADVISORY_CONSENSUS_SCHEMA = "cve-advisory-consensus-v1"


@dataclass(frozen=True)
class AdvisorySourceEvidence:
    source_name: str
    source_authority: str
    identity_kind: str
    identity_key: str
    affected_version_ranges: tuple[str, ...]
    observed_versions: tuple[str, ...]
    applicability_state: str
    trusted_affected_version_supported: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["affected_version_ranges"] = list(
            self.affected_version_ranges
        )
        payload["observed_versions"] = list(self.observed_versions)
        return payload


@dataclass(frozen=True)
class CveAdvisoryConsensus:
    schema: str
    cve_id: str | None
    state: str
    source_count: int
    source_instance_count: int
    matched_advisory_count: int
    identity_count: int
    identity_kinds: tuple[str, ...]
    sources: tuple[str, ...]
    authorities: tuple[str, ...]
    evidence: tuple[AdvisorySourceEvidence, ...]
    ambiguity_reasons: tuple[str, ...]
    range_sets_equal: bool
    cross_source_agreement: bool
    agreed_applicability_state: str | None
    exploitability_confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["identity_kinds"] = list(self.identity_kinds)
        payload["sources"] = list(self.sources)
        payload["authorities"] = list(self.authorities)
        payload["evidence"] = [
            item.to_dict() for item in self.evidence
        ]
        payload["ambiguity_reasons"] = list(self.ambiguity_reasons)
        return payload


def _identity_key(entry: CveAdvisoryEntry) -> str:
    if entry.identity_kind == "cpe":
        return f"cpe:{entry.vendor}:{entry.product}"
    return (
        f"package:{entry.package_ecosystem}:"
        f"{entry.package_name}"
    )


def build_cve_advisory_consensus(
    finding: Any,
    catalogs: Iterable[CveAdvisoryCatalog],
    *,
    fingerprint_versions: Iterable[str] = (),
    package_version: str | None = None,
) -> CveAdvisoryConsensus:
    cve_ids = finding_cve_ids(finding)
    if len(cve_ids) != 1:
        return CveAdvisoryConsensus(
            schema=CVE_ADVISORY_CONSENSUS_SCHEMA,
            cve_id=None,
            state="not_applicable",
            source_count=0,
            source_instance_count=0,
            matched_advisory_count=0,
            identity_count=0,
            identity_kinds=(),
            sources=(),
            authorities=(),
            evidence=(),
            ambiguity_reasons=(),
            range_sets_equal=False,
            cross_source_agreement=False,
            agreed_applicability_state=None,
            exploitability_confirmed=False,
        )

    cve_id = cve_ids[0]
    normalized_fingerprint_versions = tuple(
        sorted(
            {
                str(item).strip()
                for item in fingerprint_versions
                if str(item).strip()
            }
        )
    )
    normalized_package_version = (
        str(package_version).strip()
        if isinstance(package_version, str)
        and package_version.strip()
        else None
    )

    evidence: list[AdvisorySourceEvidence] = []
    source_instances: set[tuple[str, str, str]] = set()
    source_authorities: set[str] = set()

    for catalog in catalogs:
        matches = find_verified_cve_advisories(
            catalog,
            cve_id=cve_id,
            vendor=getattr(finding, "vendor", None),
            product=getattr(finding, "product", None),
            package_ecosystem=getattr(
                finding,
                "package_ecosystem",
                None,
            ),
            package_name=getattr(finding, "package_name", None),
        )
        if not matches:
            continue

        source_instances.add(
            (
                catalog.source_authority,
                catalog.source_name,
                catalog.source_digest_sha256,
            )
        )
        source_authorities.add(catalog.source_authority)
        for entry in matches:
            observed_versions = (
                (normalized_package_version,)
                if (
                    entry.identity_kind == "package"
                    and normalized_package_version is not None
                )
                else (
                    ()
                    if entry.identity_kind == "package"
                    else normalized_fingerprint_versions
                )
            )
            applicability = build_affected_version_range_evidence(
                finding,
                observed_versions=observed_versions,
                ranges_override=entry.affected_version_ranges,
                range_source_override=(
                    f"{catalog.source_name}:{entry.cve_id}"
                ),
                range_source_verified_override=True,
            )
            evidence.append(
                AdvisorySourceEvidence(
                    source_name=catalog.source_name,
                    source_authority=catalog.source_authority,
                    identity_kind=entry.identity_kind,
                    identity_key=_identity_key(entry),
                    affected_version_ranges=(
                        entry.affected_version_ranges
                    ),
                    observed_versions=observed_versions,
                    applicability_state=applicability.state,
                    trusted_affected_version_supported=(
                        applicability.trusted_affected_version_supported
                    ),
                )
            )

    evidence.sort(
        key=lambda item: (
            item.identity_key,
            item.source_authority,
            item.source_name,
            item.affected_version_ranges,
        )
    )
    if not evidence:
        return CveAdvisoryConsensus(
            schema=CVE_ADVISORY_CONSENSUS_SCHEMA,
            cve_id=cve_id,
            state="not_available",
            source_count=0,
            source_instance_count=0,
            matched_advisory_count=0,
            identity_count=0,
            identity_kinds=(),
            sources=(),
            authorities=(),
            evidence=(),
            ambiguity_reasons=(),
            range_sets_equal=False,
            cross_source_agreement=False,
            agreed_applicability_state=None,
            exploitability_confirmed=False,
        )

    identity_keys = {item.identity_key for item in evidence}
    identity_kinds = tuple(
        sorted({item.identity_kind for item in evidence})
    )
    sources = tuple(sorted({item.source_name for item in evidence}))
    authorities = tuple(sorted(source_authorities))
    range_sets = {
        tuple(sorted(item.affected_version_ranges))
        for item in evidence
    }
    range_sets_equal = len(range_sets) == 1
    source_count = len(source_authorities)
    source_instance_count = len(source_instances)

    ambiguity: set[str] = set()
    agreement = False
    agreed_applicability_state: str | None = None

    applicability_states = {
        item.applicability_state for item in evidence
    }
    if len(identity_keys) > 1:
        state = "parallel_unbound_identities"
        ambiguity.add("parallel_unbound_advisory_identities")
    elif source_count < 2:
        if (
            source_instance_count > 1
            and "affected" in applicability_states
            and "not_affected" in applicability_states
        ):
            state = "same_authority_snapshot_conflict"
            ambiguity.add(
                "same_authority_advisory_snapshot_conflict"
            )
        else:
            state = "single_source"
    else:
        if applicability_states == {"affected"}:
            state = "exact_identity_applicability_agreement"
            agreement = True
            agreed_applicability_state = "affected"
        elif applicability_states == {"not_affected"}:
            state = "exact_identity_applicability_agreement"
            agreement = True
            agreed_applicability_state = "not_affected"
            ambiguity.add("cross_source_advisory_not_affected")
        elif (
            "affected" in applicability_states
            and "not_affected" in applicability_states
        ):
            state = "exact_identity_applicability_conflict"
            ambiguity.add(
                "cross_source_advisory_applicability_conflict"
            )
        else:
            state = "inconclusive_cross_source"
            ambiguity.add("inconclusive_cross_source_advisory")

    return CveAdvisoryConsensus(
        schema=CVE_ADVISORY_CONSENSUS_SCHEMA,
        cve_id=cve_id,
        state=state,
        source_count=source_count,
        source_instance_count=source_instance_count,
        matched_advisory_count=len(evidence),
        identity_count=len(identity_keys),
        identity_kinds=identity_kinds,
        sources=sources,
        authorities=authorities,
        evidence=tuple(evidence),
        ambiguity_reasons=tuple(sorted(ambiguity)),
        range_sets_equal=range_sets_equal,
        cross_source_agreement=agreement,
        agreed_applicability_state=agreed_applicability_state,
        exploitability_confirmed=False,
    )
