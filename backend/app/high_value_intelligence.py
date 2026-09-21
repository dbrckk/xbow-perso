from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


@dataclass(frozen=True)
class PublicCaseLesson:
    case_id: str
    family: str
    title: str
    source_url: str
    published_at: str
    documented_reward_usd: int | None
    signals: tuple[str, ...]
    observation_goals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signals"] = list(self.signals)
        payload["observation_goals"] = list(self.observation_goals)
        return payload


@dataclass(frozen=True)
class HighValueFocus:
    family: str
    score: int
    reasons: tuple[str, ...]
    matched_case_ids: tuple[str, ...]
    observation_goals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["matched_case_ids"] = list(self.matched_case_ids)
        payload["observation_goals"] = list(self.observation_goals)
        return payload


_CASES = (
    PublicCaseLesson(
        case_id="h1-3000510",
        family="alternate-representation-access-control",
        title="Sensitive attributes exposed by report JSON serialization",
        source_url="https://www.hackerone.com/blog/hai-insight-agent-case-study",
        published_at="2025",
        documented_reward_usd=25000,
        signals=(".json", "json", "rails", "serializer", "api"),
        observation_goals=(
            "compare the same authorized object across HTML, JSON, and API representations",
            "compare field visibility across tester-owned roles without collecting third-party PII",
            "flag framework or serializer changes that alter response shape",
        ),
    ),
    PublicCaseLesson(
        case_id="h1-graphql-authz-2024",
        family="graphql-authorization",
        title="GraphQL authorization gap enabled authentication bypass",
        source_url="https://www.hackerone.com/blog/how-graphql-bug-resulted-authentication-bypass",
        published_at="2024-07-29",
        documented_reward_usd=None,
        signals=("graphql", "/graphql", "mutation", "apollo"),
        observation_goals=(
            "map GraphQL operations exposed to each authorized test role",
            "compare object and field visibility between roles",
            "treat sensitive mutations as authorization boundaries rather than relying on introspection state",
        ),
    ),
    PublicCaseLesson(
        case_id="h1-graphql-disclosure-2019",
        family="graphql-data-segregation",
        title="GraphQL object exposure disclosed confidential platform data",
        source_url="https://www.hackerone.com/blog/8-high-impact-bugs-and-how-hackerone-customers-avoided-breach-information-disclosure",
        published_at="2019",
        documented_reward_usd=20000,
        signals=("graphql", "/graphql", "user", "team"),
        observation_goals=(
            "compare nested object fields across authorized test identities",
            "separate intentionally public fields from confidential relationship data",
            "prefer minimal proof using researcher-owned records",
        ),
    ),
    PublicCaseLesson(
        case_id="h1-mfa-bypass-2024",
        family="authentication-state-machine",
        title="Inadequate authentication logic led to MFA bypass and account takeover",
        source_url="https://www.hackerone.com/blog/how-inadequate-authentication-logic-led-mfa-bypass-and-account-takeover",
        published_at="2024-11-20",
        documented_reward_usd=None,
        signals=("mfa", "2fa", "otp", "login", "session", "password", "reset", "oauth"),
        observation_goals=(
            "model authentication as a state machine across researcher-owned accounts",
            "compare session privilege before and after every authentication transition",
            "look for alternate flows that skip a required state without brute force",
        ),
    ),
    PublicCaseLesson(
        case_id="h1-ssrf-cloud-2021",
        family="server-side-fetch-boundaries",
        title="SSRF reports demonstrated cloud and internal-network impact",
        source_url="https://www.hackerone.com/blog/spotlight-server-side",
        published_at="2021-05-25",
        documented_reward_usd=None,
        signals=("webhook", "callback", "fetch", "import", "preview", "pdf", "render", "image", "url="),
        observation_goals=(
            "identify server-side URL consumers from documented in-scope functionality",
            "verify scheme, redirect, and destination controls using benign researcher-controlled endpoints",
            "avoid internal-network enumeration and cloud metadata access unless the program explicitly permits it",
        ),
    ),
)


def public_case_lessons() -> tuple[PublicCaseLesson, ...]:
    return _CASES


def _surface_tokens(graph: ObservationGraph) -> set[str]:
    tokens: set[str] = set()
    for kind in ("endpoint", "form", "technology"):
        for item in graph.by_kind(kind):
            value = str(item.value).lower()
            tokens.add(value)
            metadata = item.metadata if isinstance(item.metadata, dict) else {}
            for key in ("input_names", "method"):
                raw = metadata.get(key)
                if isinstance(raw, list):
                    tokens.update(str(part).lower() for part in raw)
                elif raw:
                    tokens.add(str(raw).lower())
    return tokens


def build_high_value_intelligence(
    graph: ObservationGraph,
    *,
    limit: int = 6,
) -> dict[str, Any]:
    """Rank public-case lessons against observed, already-authorized surface data.

    This is advisory only. It does not create payloads, execute requests, expand
    scope, or assert that a vulnerability exists.
    """
    if not 1 <= limit <= 20:
        raise ValueError("high-value intelligence limit must be between 1 and 20")

    surface = _surface_tokens(graph)
    joined = "\n".join(sorted(surface))
    grouped: dict[str, dict[str, Any]] = {}

    for case in _CASES:
        matched = tuple(signal for signal in case.signals if signal in joined)
        score = 35 + min(45, len(matched) * 15)
        reasons = ["public resolved-case lesson"]
        if matched:
            reasons.append("surface signals: " + ", ".join(matched[:5]))
        if case.documented_reward_usd:
            reasons.append(f"documented case reward: ${case.documented_reward_usd:,}")

        current = grouped.setdefault(
            case.family,
            {
                "score": 0,
                "reasons": set(),
                "case_ids": set(),
                "goals": set(),
            },
        )
        current["score"] = max(int(current["score"]), score)
        current["reasons"].update(reasons)
        current["case_ids"].add(case.case_id)
        current["goals"].update(case.observation_goals)

    focuses = [
        HighValueFocus(
            family=family,
            score=int(payload["score"]),
            reasons=tuple(sorted(payload["reasons"])),
            matched_case_ids=tuple(sorted(payload["case_ids"])),
            observation_goals=tuple(sorted(payload["goals"])),
        )
        for family, payload in grouped.items()
    ]
    focuses.sort(key=lambda item: (-item.score, item.family))

    return {
        "focuses": [item.to_dict() for item in focuses[:limit]],
        "cases": [item.to_dict() for item in _CASES],
        "surface_signal_count": len(surface),
        "advisory_only": True,
        "scope_expansion": False,
        "automatic_exploitation": False,
    }
