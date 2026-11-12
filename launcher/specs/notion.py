"""The `notion` spec backend (#951, #937 §6 and §7), with the custody and scope set on #943.

`NotionSource` is a `SpecSource` that talks to Notion's API as the `productswarm` internal
integration. Standard library only (`urllib.request`), and no model calls (#937 §7).

**Token custody (#943, Part A option 2).** The token lives in
`~/.config/productswarm/notion.token` with mode 0600, on the owner's machine only.
`load_token()` reads it at call time. Nothing here reads `NOTION_TOKEN` or any other
environment variable, and nothing writes the token to `os.environ`, a subprocess, a log, the
event log or an exception message. Only the `NotionSource` instance holds it, and its
`repr` doesn't show it.

**Scope (#943, Part A).** The integration has Read content, Update content, Read comments
and Insert comments, and nothing else. Every request goes through `_check_scope`, which
allows only the calls those cover: reading blocks, databases and pages, querying a database,
updating a Features page's bridge-written properties, and listing and adding comments. No
call creates a page or database, reads users, or writes a page body.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pwd
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .source import (
    Feature, FeatureStatus, SchemaError, Spec, SPEC_HEADINGS, require_bridge_status,
)

API = "https://api.notion.com"

# Pinned in code (#937 §6). 2022-06-28 is the last version that treats a database as one
# table: from 2025-09-03 Notion splits a database into data sources, and querying moves to
# /v1/data_sources. Moving off this pin is a code change, never a config one.
NOTION_VERSION = "2022-06-28"

TOKEN_FILE = ".config/productswarm/notion.token"

# §6's layout. Property name → Notion property type.
INITIATIVES_DB = "Initiatives"
FEATURES_DB = "Features"
INITIATIVE_PROPS = {"Name": "title", "Goal": "url", "Status": "status"}
INITIATIVE_STATUSES = ("Planned", "Active", "Done")
FEATURE_PROPS = {
    "Name": "title", "ID": "unique_id", "Initiative": "relation", "Status": "status",
    "Issue": "url", "PR": "url", "Last synced": "date",
}
FEATURE_ID_PREFIX = "FEAT"

# The Features properties the bridge writes (§6, "Written by"). A page update may touch
# these and nothing else: never Name, ID, Initiative, and never the page body (§5.4).
BRIDGE_PROPS = frozenset({"Status", "Issue", "PR", "Last synced"})

# Notion's limit on one rich-text segment.
_RICH_TEXT_MAX = 2000
_PAGE_SIZE = 100
_MAX_DEPTH = 3   # nested blocks read under a spec heading (toggles, nested list items)

Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, bytes]"]


class TokenError(Exception):
    """The token file is missing, empty or not private. Its message never holds the token."""


class NotionError(Exception):
    """A Notion request failed, or the backend refused to make it (#943 scope)."""


class ScopeError(NotionError):
    """A request outside the integration's four capabilities (#943 Part A). Never sent."""


# --- token custody -----------------------------------------------------------------------

def token_path() -> Path:
    """`~/.config/productswarm/notion.token`, with home from the password database rather
    than `$HOME`, so no environment variable can move where the token is read from."""
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / TOKEN_FILE


def load_token(path: Optional[os.PathLike] = None) -> str:
    """Read the Notion token from its file at call time, strip it and return it.

    Raises TokenError, and never falls back to anything else (no environment variable), when
    the file is missing, isn't a regular file owned by this user, has any permission beyond
    0600 (readable, writable or executable by group or others), or is empty.
    """
    p = Path(path) if path is not None else token_path()
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise TokenError(f"no Notion token file at {p}: create it with mode 0600") from None
    except OSError as e:
        raise TokenError(f"can't open the Notion token file {p}: {e.strerror}") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise TokenError(f"the Notion token file {p} is not a regular file")
        if st.st_uid != os.getuid():
            raise TokenError(f"the Notion token file {p} is not owned by this user")
        mode = stat.S_IMODE(st.st_mode)
        if mode & ~0o600:
            raise TokenError(
                f"the Notion token file {p} has mode {mode:04o}; it must be 0600 or stricter "
                f"(chmod 600 {p})")
        with os.fdopen(fd, "rb") as f:
            fd = -1
            raw = f.read()
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise TokenError(f"the Notion token file {p} is not UTF-8 text") from None
    if not token:
        raise TokenError(f"the Notion token file {p} is empty")
    return token


# --- transport ---------------------------------------------------------------------------

def urllib_transport(method: str, url: str, headers: dict,
                     body: Optional[bytes]) -> tuple[int, bytes]:
    """The real transport. Returns (status, body); raises NotionError on a network failure,
    with no request detail in the message (the headers hold the token)."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise NotionError(f"Notion request failed: {type(reason).__name__}") from None


# --- scope -------------------------------------------------------------------------------

_ID = r"[0-9a-fA-F-]{32,36}"
# (method, path) → the capability that covers it (#943 Part A). Nothing else is ever sent.
_ALLOWED = (
    ("GET", re.compile(rf"/v1/blocks/{_ID}/children"), "read content"),
    ("GET", re.compile(rf"/v1/databases/{_ID}"), "read content"),
    ("POST", re.compile(rf"/v1/databases/{_ID}/query"), "read content"),
    ("GET", re.compile(rf"/v1/pages/{_ID}"), "read content"),
    ("PATCH", re.compile(rf"/v1/pages/{_ID}"), "update content (properties only)"),
    ("GET", re.compile(r"/v1/comments"), "read comments"),
    ("POST", re.compile(r"/v1/comments"), "insert comments"),
)


def _check_scope(method: str, path: str, payload: Optional[dict]) -> None:
    """Raise ScopeError unless the call is one the integration's capabilities allow."""
    if not any(m == method and rx.fullmatch(path) for m, rx, _ in _ALLOWED):
        raise ScopeError(f"{method} {path} is outside the integration's scope (#943)")
    if method == "PATCH":
        # Properties only: no body, no archive, no icon or cover, and only bridge properties.
        if not payload or set(payload) != {"properties"}:
            raise ScopeError("a page update may carry only properties (#937 §5.4)")
        extra = set(payload["properties"]) - BRIDGE_PROPS
        if extra:
            raise ScopeError(f"the bridge may not write {', '.join(sorted(extra))} (#937 §6)")
    if method == "POST" and path == "/v1/comments":
        parent = (payload or {}).get("parent") or {}
        if set(parent) != {"page_id"}:
            raise ScopeError("a comment must go on a feature page")


# --- helpers -----------------------------------------------------------------------------

def _plain(rich: list) -> str:
    return "".join(r.get("plain_text") or (r.get("text") or {}).get("content", "")
                   for r in rich or [])


def _uuid(s: str) -> str:
    """Notion ids compare without dashes, lowercase."""
    return (s or "").replace("-", "").lower()


def _feature_number(feature_id: str) -> int:
    m = re.fullmatch(rf"{FEATURE_ID_PREFIX}-(\d+)", feature_id or "")
    if not m:
        raise ValueError(f"not a feature id: {feature_id!r} (expected {FEATURE_ID_PREFIX}-n)")
    return int(m.group(1))


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _chunks(text: str) -> list[str]:
    return [text[i:i + _RICH_TEXT_MAX] for i in range(0, len(text), _RICH_TEXT_MAX)] or [""]


_LINE_PREFIX = {
    "bulleted_list_item": "- ",
    "numbered_list_item": "1. ",
    "quote": "> ",
}
_TEXT_BLOCKS = {"paragraph", "bulleted_list_item", "numbered_list_item", "quote", "callout",
                "code", "to_do", "toggle"}
_HEADINGS = {"heading_1", "heading_2", "heading_3"}


# --- the backend -------------------------------------------------------------------------

class NotionSource:
    """The `notion` SpecSource (#937 §7). Built only inside `swarm specs`.

    `parent_page` is the "productswarm specs" page the integration is shared with. `token`
    defaults to `load_token()`. `transport(method, url, headers, body) -> (status, body)`
    makes every request; tests pass a fake, so they need no network and no token.
    `clock()` returns the ISO time written to `Last synced`.
    """

    name = "notion"
    simulated = False

    def __init__(self, parent_page: str, token: Optional[str] = None,
                 transport: Optional[Transport] = None,
                 clock: Optional[Callable[[], str]] = None):
        self.parent_page = parent_page
        self._token = token if token is not None else load_token()
        self._transport = transport or urllib_transport
        self._clock = clock or _now
        self._dbs: Optional[dict] = None          # {"initiatives": id, "features": id}
        self._pages: dict[str, str] = {}          # FEAT-n → page id

    def __repr__(self) -> str:
        return f"NotionSource(parent_page={self.parent_page!r})"

    __str__ = __repr__

    # -- requests

    def _request(self, method: str, path: str, payload: Optional[dict] = None,
                 query: Optional[dict] = None) -> dict:
        _check_scope(method, path, payload)
        url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        status, raw = self._transport(method, url, headers, body)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            data = {}
        if not 200 <= status < 300:
            code = data.get("code", "error") if isinstance(data, dict) else "error"
            msg = data.get("message", "") if isinstance(data, dict) else ""
            raise NotionError(self._scrub(f"Notion {method} {path}: {status} {code}: {msg}"))
        return data

    def _scrub(self, text: str) -> str:
        """Belt and braces: no error message ever carries the token."""
        return text.replace(self._token, "[token]") if self._token else text

    def _paged(self, method: str, path: str, payload: Optional[dict] = None,
               query: Optional[dict] = None) -> list[dict]:
        results, cursor = [], None
        while True:
            if method == "GET":
                q = dict(query or {}, page_size=_PAGE_SIZE)
                if cursor:
                    q["start_cursor"] = cursor
                data = self._request(method, path, query=q)
            else:
                p = dict(payload or {}, page_size=_PAGE_SIZE)
                if cursor:
                    p["start_cursor"] = cursor
                data = self._request(method, path, payload=p)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                return results
            cursor = data.get("next_cursor")
            if not cursor:
                return results

    # -- adopt

    def adopt(self, parent_page: Optional[str] = None) -> dict:
        """Find the Initiatives and Features databases under the "productswarm specs" page
        and check them against #937 §6. Returns {"initiatives": id, "features": id}.

        Raises SchemaError on any mismatch: a database missing or doubled, a property
        missing or of the wrong type, a status option missing or unknown, the relation
        pointing elsewhere. It never creates or changes a database (#943).
        """
        parent = parent_page or self.parent_page
        found: dict[str, list[str]] = {}
        for block in self._paged("GET", f"/v1/blocks/{parent}/children"):
            if block.get("type") == "child_database":
                title = (block.get("child_database") or {}).get("title", "").strip()
                found.setdefault(title, []).append(block["id"])
        ids = {}
        for title in (INITIATIVES_DB, FEATURES_DB):
            hits = found.get(title, [])
            if len(hits) != 1:
                raise SchemaError(
                    f"expected one {title!r} database under the specs page, found {len(hits)}")
            ids[title] = hits[0]

        init_db = self._request("GET", f"/v1/databases/{ids[INITIATIVES_DB]}")
        _check_props(INITIATIVES_DB, init_db, INITIATIVE_PROPS)
        _check_options(INITIATIVES_DB, init_db, INITIATIVE_STATUSES)

        feat_db = self._request("GET", f"/v1/databases/{ids[FEATURES_DB]}")
        _check_props(FEATURES_DB, feat_db, FEATURE_PROPS)
        _check_options(FEATURES_DB, feat_db, tuple(s.value for s in FeatureStatus))
        props = feat_db["properties"]
        prefix = (props["ID"].get("unique_id") or {}).get("prefix")
        if prefix != FEATURE_ID_PREFIX:
            raise SchemaError(f"Features.ID prefix is {prefix!r}, expected {FEATURE_ID_PREFIX!r}")
        target = (props["Initiative"].get("relation") or {}).get("database_id", "")
        if _uuid(target) != _uuid(ids[INITIATIVES_DB]):
            raise SchemaError("Features.Initiative does not relate to the Initiatives database")

        self.parent_page = parent
        self._dbs = {"initiatives": ids[INITIATIVES_DB], "features": ids[FEATURES_DB]}
        return dict(self._dbs)

    def _features_db(self) -> str:
        if self._dbs is None:
            self.adopt()
        return self._dbs["features"]

    # -- reads

    def list_features(self, initiative_id: str) -> list[Feature]:
        rows = self._paged("POST", f"/v1/databases/{self._features_db()}/query", payload={
            "filter": {"property": "Initiative", "relation": {"contains": initiative_id}},
        })
        features = [self._feature(row) for row in rows]
        return sorted(features, key=lambda f: _feature_number(f.id))

    def _feature(self, page: dict) -> Feature:
        props = page.get("properties") or {}
        for prop, kind in FEATURE_PROPS.items():
            if (props.get(prop) or {}).get("type") != kind:
                raise SchemaError(f"feature page {page.get('id')} has no {kind} {prop!r}")
        uid = props["ID"]["unique_id"] or {}
        if uid.get("prefix") != FEATURE_ID_PREFIX or uid.get("number") is None:
            raise SchemaError(f"feature page {page.get('id')} has no {FEATURE_ID_PREFIX}-n ID")
        fid = f"{FEATURE_ID_PREFIX}-{uid['number']}"
        status_name = (props["Status"]["status"] or {}).get("name")
        try:
            status = FeatureStatus(status_name)
        except ValueError:
            raise SchemaError(f"{fid} has unknown status {status_name!r}") from None
        rel = props["Initiative"]["relation"] or []
        if len(rel) != 1:
            raise SchemaError(f"{fid} must belong to exactly one initiative, has {len(rel)}")
        synced = props["Last synced"]["date"]
        self._pages[fid] = page["id"]
        return Feature(
            id=fid,
            name=_plain(props["Name"]["title"]).strip(),
            url=page.get("url", ""),
            initiative_id=rel[0]["id"],
            status=status,
            issue_url=props["Issue"]["url"] or None,
            pr_url=props["PR"]["url"] or None,
            last_edited=page.get("last_edited_time"),
            last_synced=(synced or {}).get("start"),
        )

    def _page_id(self, feature_id: str) -> str:
        if feature_id in self._pages:
            return self._pages[feature_id]
        number = _feature_number(feature_id)
        rows = self._request("POST", f"/v1/databases/{self._features_db()}/query", payload={
            "filter": {"property": "ID", "unique_id": {"equals": number}},
            "page_size": 2,
        }).get("results") or []
        if len(rows) != 1:
            raise SchemaError(f"expected one feature {feature_id}, found {len(rows)}")
        feature = self._feature(rows[0])
        if feature.id != feature_id:
            raise SchemaError(f"looked up {feature_id}, got {feature.id}")
        return self._pages[feature_id]

    def get_spec(self, feature_id: str) -> Spec:
        """Parse the feature's page body by §6's fixed headings.

        Every heading (levels 1 to 3) starts a section and must be one §6 defines;
        `Spec.from_sections` raises SchemaError otherwise. Text before the first heading is
        ignored. Under `Acceptance criteria`, only to-do items are criteria: a bullet there
        isn't one, so a list of bullets leaves the feature not pullable rather than guessed at.
        """
        sections: dict[str, object] = {}
        current: Optional[str] = None
        lines: list[str] = []

        def close():
            if current is None:
                return
            if current == "Acceptance criteria":
                sections[current] = list(criteria)
            else:
                sections[current] = "\n".join(lines)

        criteria: list[tuple[str, bool]] = []
        for block in self._children(self._page_id(feature_id)):
            kind = block.get("type")
            if kind in _HEADINGS:
                close()
                current = _plain(block[kind].get("rich_text")).strip()
                if current in sections:
                    raise SchemaError(f"{feature_id}: heading {current!r} appears twice")
                lines, criteria = [], []
                # A toggle heading keeps its section's content as its children.
                if block.get("has_children"):
                    self._collect(block["id"], current, lines, criteria, depth=1)
                continue
            if current is None:
                continue
            self._take(block, current, lines, criteria, depth=0)
        close()
        return Spec.from_sections(sections)

    def _children(self, block_id: str) -> list[dict]:
        return self._paged("GET", f"/v1/blocks/{block_id}/children")

    def _collect(self, block_id, section, lines, criteria, depth):
        if depth > _MAX_DEPTH:
            return
        for child in self._children(block_id):
            if child.get("type") in _HEADINGS:
                raise SchemaError(f"heading nested inside {section!r}")
            self._take(child, section, lines, criteria, depth)

    def _take(self, block, section, lines, criteria, depth):
        kind = block.get("type")
        if kind not in _TEXT_BLOCKS:
            return   # images, dividers, embeds: not spec text
        text = _plain((block.get(kind) or {}).get("rich_text"))
        if section == "Acceptance criteria":
            if kind == "to_do" and text.strip():
                criteria.append((text.strip(), bool(block["to_do"].get("checked"))))
        else:
            indent = "  " * depth
            if kind == "to_do":
                box = "[x]" if block["to_do"].get("checked") else "[ ]"
                lines.append(f"{indent}- {box} {text}")
            else:
                lines.append(indent + _LINE_PREFIX.get(kind, "") + text)
        if block.get("has_children"):
            self._collect(block["id"], section, lines, criteria, depth + 1)

    # -- writes: properties and comments only, never a page body (§5.4)

    def _update(self, feature_id: str, properties: dict) -> None:
        properties = dict(properties, **{"Last synced": {"date": {"start": self._clock()}}})
        self._request("PATCH", f"/v1/pages/{self._page_id(feature_id)}",
                      payload={"properties": properties})

    def set_status(self, feature_id: str, status: FeatureStatus,
                   reason: Optional[str] = None) -> None:
        """Write Status and Last synced. Refuses Draft and Ready (the owner's) before any
        request. A Blocked reason goes on the feature as a marked comment, since §6 has no
        property for it, so the same reason is written once."""
        s = require_bridge_status(status)
        self._update(feature_id, {"Status": {"status": {"name": s.value}}})
        if s is FeatureStatus.BLOCKED and reason:
            line = " ".join(reason.split())
            digest = hashlib.sha256(line.encode("utf-8")).hexdigest()[:12]
            self.comment(feature_id, f"Blocked: {line}", f"swarm:blocked={digest}")

    def set_links(self, feature_id: str, issue_url: Optional[str] = None,
                  pr_url: Optional[str] = None) -> None:
        """Write Issue and PR (and Last synced); None leaves a link as it is."""
        props = {}
        if issue_url is not None:
            props["Issue"] = {"url": issue_url}
        if pr_url is not None:
            props["PR"] = {"url": pr_url}
        if props:
            self._update(feature_id, props)

    def comment(self, feature_id: str, body: str, marker: str) -> bool:
        """List the page's comments first; write nothing when one already carries `marker`.

        Notion comments can't hide text, so the marker is the comment's last line, in code
        style. A comment carries the marker when it's one of its whitespace-separated words,
        so `swarm:pr=1` doesn't match `swarm:pr=12`.
        """
        marker = marker.strip()
        if not marker or any(ch.isspace() for ch in marker):
            raise ValueError("a comment marker must be one non-empty word")
        page = self._page_id(feature_id)
        for c in self._paged("GET", "/v1/comments", query={"block_id": page}):
            if marker in _plain(c.get("rich_text")).split():
                return False
        rich = [{"type": "text", "text": {"content": part}} for part in _chunks(body.rstrip())]
        rich.append({"type": "text", "text": {"content": "\n"}})
        rich.append({"type": "text", "text": {"content": marker},
                     "annotations": {"code": True}})
        self._request("POST", "/v1/comments",
                      payload={"parent": {"page_id": page}, "rich_text": rich})
        return True


def _check_props(db_name: str, db: dict, want: dict) -> None:
    props = db.get("properties") or {}
    for prop, kind in want.items():
        got = (props.get(prop) or {}).get("type")
        if got is None:
            raise SchemaError(f"{db_name} database has no {prop!r} property")
        if got != kind:
            raise SchemaError(f"{db_name}.{prop} is {got}, expected {kind}")


def _check_options(db_name: str, db: dict, want: tuple) -> None:
    status = db["properties"]["Status"].get("status") or {}
    got = {o.get("name") for o in status.get("options") or []}
    missing = [s for s in want if s not in got]
    unknown = sorted(got - set(want))
    if missing:
        raise SchemaError(f"{db_name}.Status lacks {', '.join(missing)}")
    if unknown:
        raise SchemaError(f"{db_name}.Status has unknown status {', '.join(unknown)}")
