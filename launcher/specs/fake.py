"""The `fake` spec backend (#941, #937 §7): a SpecSource read from a JSON fixture.

Tests use it, phase 1 runs `pull`, `diff` and `push` against it (#937 §11), and the
Productboard demo uses it under a "simulated" label. Writes change only the in-memory state
and are logged in `writes`; `dump` saves the state back as a fixture so a manual run can be
repeated or continued. Standard library only.

Fixture layout (§6's databases, Notion-shaped):

    {
      "initiatives": [
        {"id": "<page id>", "url": "...",
         "properties": {"Name": "...", "Goal": "<Goal issue URL>", "Status": "Active"}}
      ],
      "features": [
        {"url": "...", "last_edited_time": "2026-11-01T09:00:00Z",
         "properties": {"Name": "...", "ID": "FEAT-1", "Initiative": "<initiative id>",
                        "Status": "Ready", "Issue": null, "PR": null, "Last synced": null},
         "spec": {"Problem": "...", "Acceptance criteria": [{"text": "...", "checked": false}]},
         "comments": [{"body": "...", "marker": "swarm:pr=12"}]}
      ]
    }

Every property §6 lists must be present (Issue, PR and Last synced may be null), and no
other. A fixture that breaks the layout raises SchemaError and loads nothing.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

from .source import (
    Feature, FeatureStatus, SPEC_HEADINGS, SchemaError, Spec, require_bridge_status,
)

INITIATIVE_PROPERTIES = ("Name", "Goal", "Status")
INITIATIVE_STATUSES = ("Planned", "Active", "Done")
FEATURE_PROPERTIES = ("Name", "ID", "Initiative", "Status", "Issue", "PR", "Last synced")
_OPTIONAL = {"Goal", "Issue", "PR", "Last synced"}
_FEATURE_ID = re.compile(r"FEAT-[1-9][0-9]*")
_TS = "%Y-%m-%dT%H:%M:%SZ"


class FakeSource:
    """A SpecSource over a JSON fixture. Reads come from the fixture; writes stay in memory."""

    name = "fake"
    simulated = True

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SchemaError(f"{self.path}: not JSON: {e}") from None
        initiatives, features, specs, comments = _parse(data)
        self.initiatives: dict[str, dict] = initiatives
        self._features: dict[str, Feature] = features
        self._specs: dict[str, Spec] = specs
        self._comments: dict[str, list[dict]] = comments
        self.writes: list[tuple[str, str, dict]] = []

    # --- SpecSource ---------------------------------------------------------------

    def list_features(self, initiative_id: str) -> list[Feature]:
        if initiative_id not in self.initiatives:
            raise KeyError(f"no initiative {initiative_id!r}")
        return [f for f in self._features.values() if f.initiative_id == initiative_id]

    def get_spec(self, feature_id: str) -> Spec:
        self._feature(feature_id)
        return self._specs[feature_id]

    def set_status(self, feature_id: str, status: FeatureStatus,
                   reason: Optional[str] = None) -> None:
        s = require_bridge_status(status)
        f = self._feature(feature_id)
        self._features[feature_id] = replace(f, status=s)
        self.writes.append(("set_status", feature_id, {"status": s.value, "reason": reason}))

    def set_links(self, feature_id: str, issue_url: Optional[str] = None,
                  pr_url: Optional[str] = None) -> None:
        f = self._feature(feature_id)
        self._features[feature_id] = replace(
            f, issue_url=f.issue_url if issue_url is None else issue_url,
            pr_url=f.pr_url if pr_url is None else pr_url)
        self.writes.append(("set_links", feature_id, {"issue_url": issue_url, "pr_url": pr_url}))

    def comment(self, feature_id: str, body: str, marker: str) -> bool:
        self._feature(feature_id)
        existing = self._comments[feature_id]
        if any(c["marker"] == marker for c in existing):
            return False
        existing.append({"body": body, "marker": marker})
        self.writes.append(("comment", feature_id, {"body": body, "marker": marker}))
        return True

    # --- simulation and persistence -----------------------------------------------

    def comments(self, feature_id: str) -> list[dict]:
        """The feature's comments, oldest first, as `{"body", "marker"}` dicts."""
        self._feature(feature_id)
        return [dict(c) for c in self._comments[feature_id]]

    def edit_spec(self, feature_id: str, **sections) -> Spec:
        """Simulate the owner editing a spec mid-run. Keywords are Spec field names
        (`problem`, `scope`, `out_of_scope`, `acceptance_criteria`, `notes`); the rest of the
        spec stays. Moves the feature's `last_edited` forward. Not a write the bridge makes,
        so it isn't logged in `writes`."""
        f = self._feature(feature_id)
        fields = {v: k for k, v in SPEC_HEADINGS.items()}
        unknown = sorted(set(sections) - set(fields))
        if unknown:
            raise TypeError(f"unknown spec field(s): {', '.join(unknown)}")
        merged = _sections(self._specs[feature_id])
        for field, value in sections.items():
            merged[fields[field]] = value
        spec = Spec.from_sections(merged)
        self._specs[feature_id] = spec
        self._features[feature_id] = replace(f, last_edited=_later(f.last_edited))
        return spec

    def dump(self, path: Union[str, Path]) -> None:
        """Write the current state as a fixture. Loading it gives the same state; the file
        matches the original only if every feature had every heading (Acceptance criteria
        may be left out), since a missing section dumps as `""`."""
        data = {
            "initiatives": list(self.initiatives.values()),
            "features": [self._dump_feature(f) for f in self._features.values()],
        }
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")

    def _dump_feature(self, f: Feature) -> dict:
        return {
            "url": f.url,
            "last_edited_time": f.last_edited,
            "properties": {
                "Name": f.name, "ID": f.id, "Initiative": f.initiative_id,
                "Status": f.status.value, "Issue": f.issue_url, "PR": f.pr_url,
                "Last synced": f.last_synced,
            },
            "spec": _sections(self._specs[f.id]),
            "comments": [dict(c) for c in self._comments[f.id]],
        }

    def _feature(self, feature_id: str) -> Feature:
        try:
            return self._features[feature_id]
        except KeyError:
            raise KeyError(f"no feature {feature_id!r}") from None


def _sections(spec: Spec) -> dict:
    """A Spec back as heading → content, the fixture's form. A missing Acceptance criteria
    heading stays missing."""
    out = {}
    for heading, field in SPEC_HEADINGS.items():
        value = getattr(spec, field)
        if field == "acceptance_criteria":
            if value is not None:
                out[heading] = [{"text": c.text, "checked": c.checked} for c in value]
        else:
            out[heading] = value
    return out


def _later(ts: Optional[str]) -> str:
    """Now, or one second after `ts` if the clock hasn't passed it (fixtures may be dated
    ahead), so an edit always moves `last_edited` strictly forward."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if ts:
        prev = _parse_ts(ts, "last_edited_time")
        if now <= prev:
            now = prev + timedelta(seconds=1)
    return now.strftime(_TS)


def _check_spec_values(spec: dict, where: str) -> None:
    """Each section is a string or null; Acceptance criteria is null or a list of
    `{"text": str, "checked": bool}`. Anything else is refused, not stringified. An
    unknown heading is reported as that first, whatever its value."""
    unknown = sorted(set(spec) - set(SPEC_HEADINGS))
    if unknown:
        raise SchemaError(f"{where}: unknown spec heading(s): {', '.join(unknown)}")
    for heading, value in spec.items():
        w = f"{where}[{heading!r}]"
        if heading != "Acceptance criteria":
            if value is not None and not isinstance(value, str):
                raise SchemaError(f"{w} must be a string or null, not {type(value).__name__}")
            continue
        if value is None:
            continue
        if not isinstance(value, list):
            raise SchemaError(f"{w} must be a list or null, not {type(value).__name__}")
        for i, item in enumerate(value):
            if (not isinstance(item, dict) or set(item) != {"text", "checked"}
                    or not isinstance(item["text"], str)
                    or not isinstance(item["checked"], bool)):
                raise SchemaError(
                    f"{w}[{i}] must be {{\"text\": string, \"checked\": bool}}: {item!r}")


def _parse_ts(ts: str, where: str) -> datetime:
    if not isinstance(ts, str):
        raise SchemaError(f"{where}: not an ISO 8601 timestamp: {ts!r}")
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise SchemaError(f"{where}: not an ISO 8601 timestamp: {ts!r}") from None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# --- loading -------------------------------------------------------------------------

def _parse(data) -> tuple[dict, dict, dict, dict]:
    """Validate the whole fixture before returning any of it."""
    if not isinstance(data, dict) or set(data) != {"initiatives", "features"}:
        raise SchemaError("fixture must be an object with exactly 'initiatives' and 'features'")
    if not isinstance(data["initiatives"], list) or not isinstance(data["features"], list):
        raise SchemaError("'initiatives' and 'features' must be lists")

    initiatives: dict[str, dict] = {}
    for n, raw in enumerate(data["initiatives"]):
        where = f"initiatives[{n}]"
        _keys(raw, {"id", "url", "properties"}, where)
        iid = _text(raw["id"], f"{where}.id")
        if iid in initiatives:
            raise SchemaError(f"{where}: duplicate initiative id {iid!r}")
        props = _properties(raw["properties"], INITIATIVE_PROPERTIES, where)
        if props["Status"] not in INITIATIVE_STATUSES:
            raise SchemaError(f"{where}: unknown initiative Status {props['Status']!r}")
        initiatives[iid] = {"id": iid, "url": _text(raw["url"], f"{where}.url"),
                            "properties": props}

    features: dict[str, Feature] = {}
    specs: dict[str, Spec] = {}
    comments: dict[str, list[dict]] = {}
    for n, raw in enumerate(data["features"]):
        where = f"features[{n}]"
        _keys(raw, {"url", "last_edited_time", "properties", "spec", "comments"}, where)
        p = _properties(raw["properties"], FEATURE_PROPERTIES, where)
        fid = p["ID"]
        if not _FEATURE_ID.fullmatch(fid):
            raise SchemaError(f"{where}: ID {fid!r} is not FEAT-n")
        if fid in features:
            raise SchemaError(f"{where}: duplicate feature ID {fid!r}")
        if p["Initiative"] not in initiatives:
            raise SchemaError(f"{where}: Initiative {p['Initiative']!r} is not in the fixture")
        try:
            status = FeatureStatus(p["Status"])
        except ValueError:
            raise SchemaError(f"{where}: unknown Status {p['Status']!r}") from None
        edited = raw["last_edited_time"]
        if edited is not None:
            _parse_ts(edited, f"{where}.last_edited_time")
        if not isinstance(raw["spec"], dict):
            raise SchemaError(f"{where}.spec must be an object of heading → content")
        _check_spec_values(raw["spec"], f"{where}.spec")
        try:
            spec = Spec.from_sections(raw["spec"])
        except SchemaError as e:
            raise SchemaError(f"{where}.spec: {e}") from None
        features[fid] = Feature(
            id=fid, name=p["Name"], url=_text(raw["url"], f"{where}.url"),
            initiative_id=p["Initiative"], status=status, issue_url=p["Issue"],
            pr_url=p["PR"], last_edited=edited, last_synced=p["Last synced"])
        specs[fid] = spec
        comments[fid] = _comments(raw["comments"], where)
    return initiatives, features, specs, comments


def _keys(raw, keys: set, where: str) -> None:
    if not isinstance(raw, dict):
        raise SchemaError(f"{where} must be an object")
    missing, extra = sorted(keys - set(raw)), sorted(set(raw) - keys)
    if missing:
        raise SchemaError(f"{where}: missing {', '.join(missing)}")
    if extra:
        raise SchemaError(f"{where}: unknown key(s) {', '.join(extra)}")


def _properties(raw, names: tuple, where: str) -> dict:
    where = f"{where}.properties"
    _keys(raw, set(names), where)
    out = {}
    for name in names:
        value = raw[name]
        if value is None and name in _OPTIONAL:
            out[name] = None
        else:
            out[name] = _text(value, f"{where}.{name}")
    return out


def _text(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{where} must be a non-empty string")
    return value


def _comments(raw, where: str) -> list[dict]:
    if not isinstance(raw, list):
        raise SchemaError(f"{where}.comments must be a list")
    out = []
    for n, c in enumerate(raw):
        w = f"{where}.comments[{n}]"
        _keys(c, {"body", "marker"}, w)
        if not isinstance(c["body"], str):
            raise SchemaError(f"{w}.body must be a string")
        if c["marker"] is not None and not isinstance(c["marker"], str):
            raise SchemaError(f"{w}.marker must be a string or null")
        out.append({"body": c["body"], "marker": c["marker"]})
    return out
