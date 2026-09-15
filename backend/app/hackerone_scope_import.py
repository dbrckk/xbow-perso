from __future__ import annotations

import ipaddress
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .main import ProgramRules


_MAX_SCOPE_ASSETS = 5000
_MAX_IDENTIFIER_CHARS = 2048
_MAX_POLICY_TEXT_CHARS = 8192
_MAX_RESTRICTIONS = 100
_MAX_RESTRICTION_CHARS = 1024


class HackerOneScopeImportError(RuntimeError):
    pass


def _explicit_text(
    value: Any,
    *,
    field: str,
    min_length: int = 1,
    max_length: int = _MAX_POLICY_TEXT_CHARS,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise HackerOneScopeImportError(f"HackerOne {field} must be a string")
    if value != value.strip():
        raise HackerOneScopeImportError(f"HackerOne {field} must not contain outer whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise HackerOneScopeImportError(f"HackerOne {field} contains unsafe control characters")
    if not allow_empty and len(value) < min_length:
        raise HackerOneScopeImportError(f"HackerOne {field} is required")
    if len(value) > max_length:
        raise HackerOneScopeImportError(f"HackerOne {field} is too long")
    return value


def _reviewed_at(value: Any) -> str:
    if not isinstance(value, str):
        raise HackerOneScopeImportError("HackerOne reviewed_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HackerOneScopeImportError("HackerOne reviewed_at must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HackerOneScopeImportError("HackerOne reviewed_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _restrictions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise HackerOneScopeImportError("HackerOne additional_restrictions must be a list")
    if len(value) > _MAX_RESTRICTIONS:
        raise HackerOneScopeImportError("HackerOne additional_restrictions exceeds safety limit")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        restriction = _explicit_text(
            item,
            field="additional restriction",
            max_length=_MAX_RESTRICTION_CHARS,
        )
        if restriction not in seen:
            normalized.append(restriction)
            seen.add(restriction)
    return tuple(normalized)


@dataclass(frozen=True)
class HackerOneProgramPolicy:
    """Human-reviewed HackerOne program constraints required for rule conversion.

    StructuredScope describes assets only. It does not grant automation permission,
    define a safe request rate, or capture program-specific operating constraints.
    Every field here is therefore explicit and included in an immutable preview
    snapshot before a scope can become executable ProgramRules.
    """

    authorization_reference: str
    policy_version: str
    reviewed_at: str
    reviewed_by: str
    safe_harbor_confirmed: bool
    automated_scanning: bool
    max_requests_per_second: float
    test_account_required: bool
    test_account_constraints: str
    additional_restrictions: tuple[str, ...]
    program_notes: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authorization_reference",
            _explicit_text(
                self.authorization_reference,
                field="authorization reference",
                min_length=3,
                max_length=2048,
            ),
        )
        object.__setattr__(
            self,
            "policy_version",
            _explicit_text(self.policy_version, field="policy version", max_length=256),
        )
        object.__setattr__(self, "reviewed_at", _reviewed_at(self.reviewed_at))
        object.__setattr__(
            self,
            "reviewed_by",
            _explicit_text(self.reviewed_by, field="reviewed_by", max_length=256),
        )
        if type(self.safe_harbor_confirmed) is not bool:
            raise HackerOneScopeImportError(
                "HackerOne safe_harbor_confirmed must be an explicit boolean"
            )
        if type(self.automated_scanning) is not bool:
            raise HackerOneScopeImportError(
                "HackerOne automated_scanning permission must be an explicit boolean"
            )
        rate = self.max_requests_per_second
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            raise HackerOneScopeImportError(
                "HackerOne request rate must be an explicit number"
            )
        normalized_rate = float(rate)
        if not math.isfinite(normalized_rate) or not 0 < normalized_rate <= 20:
            raise HackerOneScopeImportError(
                "HackerOne request rate must be greater than 0 and at most 20 requests/second"
            )
        object.__setattr__(self, "max_requests_per_second", normalized_rate)
        if type(self.test_account_required) is not bool:
            raise HackerOneScopeImportError(
                "HackerOne test_account_required must be an explicit boolean"
            )
        constraints = _explicit_text(
            self.test_account_constraints,
            field="test account constraints",
            max_length=4096,
            allow_empty=not self.test_account_required,
        )
        if self.test_account_required and not constraints:
            raise HackerOneScopeImportError(
                "HackerOne test account constraints are required when a test account is required"
            )
        object.__setattr__(self, "test_account_constraints", constraints)
        object.__setattr__(
            self,
            "additional_restrictions",
            _restrictions(self.additional_restrictions),
        )
        object.__setattr__(
            self,
            "program_notes",
            _explicit_text(
                self.program_notes,
                field="program notes",
                max_length=_MAX_POLICY_TEXT_CHARS,
                allow_empty=True,
            ),
        )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "authorization_reference": self.authorization_reference,
            "policy_version": self.policy_version,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
            "safe_harbor_confirmed": self.safe_harbor_confirmed,
            "automated_scanning": self.automated_scanning,
            "max_requests_per_second": self.max_requests_per_second,
            "test_account_required": self.test_account_required,
            "test_account_constraints": self.test_account_constraints,
            "additional_restrictions": list(self.additional_restrictions),
            "program_notes": self.program_notes,
        }


@dataclass(frozen=True)
class HackerOneScopeAsset:
    identifier: str
    asset_type: str
    eligible_for_submission: bool
    host_pattern: str | None
    compatible: bool
    reason: str | None = None


@dataclass(frozen=True)
class HackerOneScopePreview:
    assets: tuple[HackerOneScopeAsset, ...]
    allowed_targets: tuple[str, ...]
    denied_targets: tuple[str, ...]
    complete: bool
    conflicts: tuple[str, ...]
    unsupported: tuple[str, ...]

    def to_program_rules(
        self,
        *,
        policy: HackerOneProgramPolicy,
    ) -> ProgramRules:
        if not isinstance(policy, HackerOneProgramPolicy):
            raise HackerOneScopeImportError(
                "explicit HackerOne program policy is required before rule conversion"
            )
        if not self.complete:
            raise HackerOneScopeImportError(
                "HackerOne scope cannot be converted without resolving unsupported or conflicting assets"
            )
        if not self.allowed_targets:
            raise HackerOneScopeImportError(
                "HackerOne scope contains no compatible in-scope targets"
            )
        return ProgramRules(
            authorization_reference=policy.authorization_reference,
            allowed_targets=list(self.allowed_targets),
            denied_targets=list(self.denied_targets),
            max_requests_per_second=policy.max_requests_per_second,
            destructive_testing=False,
            denial_of_service=False,
            social_engineering=False,
            credential_attacks=False,
            automated_scanning=policy.automated_scanning,
            notes=(
                "Imported from HackerOne StructuredScope with explicit HackerOne "
                f"program policy {policy.policy_version}; destructive, denial-of-service, "
                "social-engineering, and credential-attack capabilities remain disabled."
            ),
        )


def _clean_identifier(value: Any) -> str:
    if not isinstance(value, str):
        raise HackerOneScopeImportError("HackerOne asset identifier must be a string")
    identifier = value.strip()
    if not identifier or len(identifier) > _MAX_IDENTIFIER_CHARS:
        raise HackerOneScopeImportError("HackerOne asset identifier is invalid")
    if identifier != value or any(ord(ch) < 32 or ord(ch) == 127 for ch in identifier):
        raise HackerOneScopeImportError("HackerOne asset identifier contains unsafe whitespace")
    return identifier


def _canonical_asset_type(value: Any) -> str:
    if not isinstance(value, str):
        raise HackerOneScopeImportError("HackerOne asset type must be a string")
    key = "".join(ch for ch in value.strip().lower() if ch.isalnum())
    mapping = {
        "domain": "Domain",
        "wildcard": "Wildcard",
        "ipaddress": "IpAddress",
        "url": "Url",
        "cidr": "Cidr",
        "aimodel": "AiModel",
        "androidapk": "AndroidApk",
        "androidplaystore": "AndroidPlayStore",
        "api": "Api",
        "awscloudconfig": "AwsCloudConfig",
        "azurecloudconfig": "AzureCloudConfig",
        "executable": "Executable",
        "hardware": "Hardware",
        "iosappstore": "IosAppStore",
        "iosipa": "IosIpa",
        "iostestflight": "IosTestflight",
        "otherasset": "OtherAsset",
        "smartcontract": "SmartContract",
        "sourcecode": "SourceCode",
        "windowsmicrosoftstore": "WindowsMicrosoftStore",
    }
    return mapping.get(key, value.strip())


def _ascii_domain(value: str) -> str:
    candidate = value.rstrip(".").lower()
    if (
        not candidate
        or "://" in candidate
        or "/" in candidate
        or "?" in candidate
        or "#" in candidate
        or "@" in candidate
        or ":" in candidate
        or any(ch.isspace() for ch in candidate)
    ):
        raise ValueError("not a plain domain")
    try:
        ascii_value = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("invalid IDNA domain") from exc
    labels = ascii_value.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        for label in labels
    ):
        raise ValueError("invalid domain labels")
    if len(ascii_value) > 253:
        raise ValueError("domain is too long")
    return ascii_value


def _compatible_host_pattern(asset_type: str, identifier: str) -> tuple[str | None, str | None]:
    if asset_type == "Domain":
        try:
            return _ascii_domain(identifier), None
        except ValueError:
            return None, "invalid_domain"

    if asset_type == "Wildcard":
        if not identifier.startswith("*.") or identifier.count("*") != 1:
            return None, "unsupported_wildcard_shape"
        try:
            suffix = _ascii_domain(identifier[2:])
        except ValueError:
            return None, "invalid_wildcard_domain"
        return f"*.{suffix}", None

    if asset_type == "IpAddress":
        try:
            return ipaddress.ip_address(identifier).compressed.lower(), None
        except ValueError:
            return None, "invalid_ip_address"

    if asset_type == "Url":
        try:
            parsed = urlparse(identifier)
            hostname = parsed.hostname
            username = parsed.username
            password = parsed.password
        except ValueError:
            return None, "invalid_url"
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            return None, "invalid_url"
        if username or password:
            return None, "url_contains_userinfo"
        return None, "url_scope_requires_scheme_path_aware_policy"

    if asset_type == "Cidr":
        return None, "cidr_requires_network_aware_policy"

    return None, "asset_type_not_supported_by_web_scope_engine"


def _resource_attributes(resource: Any) -> dict[str, Any]:
    if not isinstance(resource, dict) or resource.get("type") not in {
        "structured-scope",
        "structured_scope",
        "structured-scope-item",
    }:
        raise HackerOneScopeImportError("HackerOne StructuredScope resource is invalid")
    attributes = resource.get("attributes")
    if not isinstance(attributes, dict):
        raise HackerOneScopeImportError("HackerOne StructuredScope attributes are invalid")
    return attributes


def import_hackerone_structured_scope(document: dict[str, Any]) -> HackerOneScopePreview:
    if not isinstance(document, dict):
        raise HackerOneScopeImportError("HackerOne scope document must be an object")

    links = document.get("links")
    if links is not None:
        if not isinstance(links, dict):
            raise HackerOneScopeImportError("HackerOne scope document links are invalid")
        if links.get("next"):
            raise HackerOneScopeImportError(
                "HackerOne scope document is paginated; collect all pages before import"
            )

    data = document.get("data")
    if isinstance(data, dict):
        resources = [data]
    elif isinstance(data, list):
        resources = data
    else:
        raise HackerOneScopeImportError("HackerOne scope document data must be a resource or list")

    if len(resources) > _MAX_SCOPE_ASSETS:
        raise HackerOneScopeImportError("HackerOne scope exceeds 5000 asset safety limit")

    assets: list[HackerOneScopeAsset] = []
    statuses: dict[str, set[bool]] = {}
    unsupported_labels: set[str] = set()

    for resource in resources:
        attributes = _resource_attributes(resource)
        identifier = _clean_identifier(attributes.get("asset_identifier"))
        asset_type = _canonical_asset_type(attributes.get("asset_type"))
        eligible = attributes.get("eligible_for_submission")
        if not isinstance(eligible, bool):
            raise HackerOneScopeImportError(
                "HackerOne eligible_for_submission must be boolean"
            )

        host_pattern, reason = _compatible_host_pattern(asset_type, identifier)
        compatible = host_pattern is not None
        if host_pattern is not None:
            statuses.setdefault(host_pattern, set()).add(eligible)
        else:
            unsupported_labels.add(f"{asset_type}:{identifier}")

        assets.append(
            HackerOneScopeAsset(
                identifier=identifier,
                asset_type=asset_type,
                eligible_for_submission=eligible,
                host_pattern=host_pattern,
                compatible=compatible,
                reason=reason,
            )
        )

    conflicts = tuple(
        sorted(pattern for pattern, values in statuses.items() if values == {False, True})
    )
    allowed = tuple(
        sorted(pattern for pattern, values in statuses.items() if values == {True})
    )
    denied = tuple(
        sorted(pattern for pattern, values in statuses.items() if False in values)
    )
    unsupported = tuple(sorted(unsupported_labels))
    complete = not conflicts and not unsupported

    return HackerOneScopePreview(
        assets=tuple(assets),
        allowed_targets=allowed,
        denied_targets=denied,
        complete=complete,
        conflicts=conflicts,
        unsupported=unsupported,
    )
