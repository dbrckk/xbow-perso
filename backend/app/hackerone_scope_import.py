from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .main import ProgramRules


_MAX_SCOPE_ASSETS = 5000
_MAX_IDENTIFIER_CHARS = 2048


class HackerOneScopeImportError(RuntimeError):
    pass


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
        authorization_reference: str,
        max_requests_per_second: float = 2.0,
    ) -> ProgramRules:
        if not self.complete:
            raise HackerOneScopeImportError(
                "HackerOne scope cannot be converted without resolving unsupported or conflicting assets"
            )
        if not self.allowed_targets:
            raise HackerOneScopeImportError(
                "HackerOne scope contains no compatible in-scope targets"
            )
        return ProgramRules(
            authorization_reference=authorization_reference,
            allowed_targets=list(self.allowed_targets),
            denied_targets=list(self.denied_targets),
            max_requests_per_second=max_requests_per_second,
            destructive_testing=False,
            denial_of_service=False,
            social_engineering=False,
            credential_attacks=False,
            automated_scanning=True,
            notes="Imported from HackerOne StructuredScope preview; review before campaign creation.",
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
            # urllib.parse raises for malformed IPv6 brackets, invalid ports,
            # and a few other malformed netloc shapes. Treat all parser
            # failures as incompatible input rather than allowing a 500 at the
            # authenticated preview API boundary.
            return None, "invalid_url"
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            return None, "invalid_url"
        if username or password:
            return None, "url_contains_userinfo"
        # XBOW's current scope engine is host-only. Converting a URL scope to a
        # hostname would lose scheme/path/port constraints and could broaden scope.
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
        sorted(
            pattern
            for pattern, values in statuses.items()
            if values == {True}
        )
    )
    denied = tuple(
        sorted(
            pattern
            for pattern, values in statuses.items()
            if False in values
        )
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
