"""The `SpecSource` adapter boundary and the feature and spec model it passes (#940, #937 §7).

Every spec backend (`notion`, `fake`, later `productboard`) implements `SpecSource`.
`swarm specs pull / diff / push / render` talk only to this protocol, never to a backend's
API. Standard library only, and no model calls (#937 §7).

The bridge never writes a spec body, so the protocol has no method that could: it reads
specs, writes a feature's status and links, and posts marked comments.
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol, runtime_checkable


class SchemaError(Exception):
    """The source's layout doesn't match #937 §6. Pull stops on it and never guesses (§13)."""


class FeatureStatus(str, enum.Enum):
    """A feature's status, spelled exactly as in the Notion Features database (#937 §6)."""

    DRAFT = "Draft"
    READY = "Ready"
    IN_PROGRESS = "In progress"
    IN_REVIEW = "In review"
    SHIPPED = "Shipped"
    BLOCKED = "Blocked"


# The statuses the bridge may write. Draft and Ready are the owner's (#937 §6, "Written by").
BRIDGE_STATUSES = frozenset({
    FeatureStatus.IN_PROGRESS, FeatureStatus.IN_REVIEW,
    FeatureStatus.SHIPPED, FeatureStatus.BLOCKED,
})


def require_bridge_status(status) -> FeatureStatus:
    """Return `status` as a FeatureStatus, or raise ValueError if the bridge may not write it.

    Every backend's `set_status` calls this before writing anything.
    """
    try:
        s = FeatureStatus(status)
    except ValueError:
        raise ValueError(f"unknown feature status {status!r}") from None
    if s not in BRIDGE_STATUSES:
        raise ValueError(f"the bridge may not set status {s.value!r}: it is the owner's")
    return s


@dataclass(frozen=True)
class Feature:
    """One row of the source's Features database (#937 §6)."""

    id: str                          # FEAT-n
    name: str
    url: str
    initiative_id: str
    status: FeatureStatus
    issue_url: Optional[str] = None
    pr_url: Optional[str] = None
    last_edited: Optional[str] = None   # the source's own timestamp (ISO 8601); diff reads it (§5.3)
    last_synced: Optional[str] = None


@dataclass(frozen=True)
class Criterion:
    """One acceptance-criteria checklist item."""

    text: str
    checked: bool = False


# Heading in the spec page body → Spec field (#937 §6). The parser reads these and only these.
SPEC_HEADINGS = {
    "Problem": "problem",
    "Scope": "scope",
    "Out of scope": "out_of_scope",
    "Acceptance criteria": "acceptance_criteria",
    "Notes": "notes",
}


def _norm(text: Optional[str]) -> str:
    """Canonical text: LF line ends, no trailing whitespace on a line, no blank lines at
    either end. Only the hash uses it; the stored text is left as the source gave it."""
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


@dataclass(frozen=True)
class Spec:
    """A feature's spec page, by the fixed headings of #937 §6.

    `acceptance_criteria` is None when the heading is missing, and an empty tuple when the
    heading is there with no items. Either way the feature isn't pullable.
    """

    problem: str = ""
    scope: str = ""
    out_of_scope: str = ""
    acceptance_criteria: Optional[tuple[Criterion, ...]] = None
    notes: str = ""

    @classmethod
    def from_sections(cls, sections: Mapping[str, object]) -> "Spec":
        """Build a Spec from heading → content, as a parser reads it. Acceptance criteria is
        a list of Criterion, `(text, checked)` pairs or `{"text", "checked"}` dicts.
        Raises SchemaError on a heading §6 doesn't define."""
        unknown = sorted(set(sections) - set(SPEC_HEADINGS))
        if unknown:
            raise SchemaError(f"unknown spec heading(s): {', '.join(unknown)}")
        kw: dict = {}
        for heading, value in sections.items():
            field = SPEC_HEADINGS[heading]
            if field == "acceptance_criteria":
                kw[field] = None if value is None else tuple(_criterion(v) for v in value)
            else:
                kw[field] = "" if value is None else str(value)
        return cls(**kw)

    def canonical(self) -> dict:
        """The form `content_hash` hashes: every field, normalised, criteria in order."""
        ac = self.acceptance_criteria
        return {
            "problem": _norm(self.problem),
            "scope": _norm(self.scope),
            "out_of_scope": _norm(self.out_of_scope),
            "acceptance_criteria": None if ac is None
            else [{"text": _norm(c.text), "checked": bool(c.checked)} for c in ac],
            "notes": _norm(self.notes),
        }

    def content_hash(self) -> str:
        """sha256 hex of the canonical form: the same content always gives the same hash,
        whatever the key order or trailing whitespace, and any section change changes it."""
        blob = json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def pullable(self) -> tuple[bool, Optional[str]]:
        """(True, None), or (False, reason) when Acceptance criteria is missing or empty (§6)."""
        if self.acceptance_criteria is None:
            return False, "no Acceptance criteria heading"
        if not [c for c in self.acceptance_criteria if _norm(c.text)]:
            return False, "Acceptance criteria is empty"
        return True, None


def _criterion(v) -> Criterion:
    if isinstance(v, Criterion):
        return v
    if isinstance(v, Mapping):
        return Criterion(str(v.get("text", "")), bool(v.get("checked", False)))
    if isinstance(v, (tuple, list)) and len(v) == 2:
        return Criterion(str(v[0]), bool(v[1]))
    raise SchemaError(f"acceptance criterion is not a checklist item: {v!r}")


@runtime_checkable
class SpecSource(Protocol):
    """What every spec backend implements (#937 §7). Raise SchemaError when the source's
    layout doesn't match §6."""

    name: str          # e.g. "notion", "fake"; render's header line names it (§5.5)
    simulated: bool    # True for the fake backend: render says "Spec source simulated" (§5.5)

    def list_features(self, initiative_id: str) -> list[Feature]:
        """Every feature of the initiative, in any status."""
        ...

    def get_spec(self, feature_id: str) -> Spec:
        """The feature's spec page, parsed by §6's headings."""
        ...

    def set_status(self, feature_id: str, status: FeatureStatus,
                   reason: Optional[str] = None) -> None:
        """Write the feature's status, with a one-line reason for Blocked. Refuses (ValueError)
        anything outside BRIDGE_STATUSES: call `require_bridge_status` first."""
        ...

    def set_links(self, feature_id: str, issue_url: Optional[str] = None,
                  pr_url: Optional[str] = None) -> None:
        """Write the feature's Issue and PR links; None leaves a link as it is."""
        ...

    def comment(self, feature_id: str, body: str, marker: str) -> bool:
        """Post `body` on the feature, carrying the hidden `marker` (e.g. `swarm:pr=<n>`, §5.4).
        Idempotent: returns False and writes nothing when a comment with that marker exists."""
        ...
