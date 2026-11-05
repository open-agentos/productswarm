"""The authority map: who may decide what, from governance/jurisdictions.yml (#410, part 11
of #397).

A reference page (authority.html), not live data, so it isn't in state.json. One row per
domain: who decides (agents blue, owner amber), owner, ratify, vote-eligible and default
shape, with the domain's in-force records from governance/INDEX.md (the rows the governance
section already parses), counted and linked to decisions.html.

Stdlib only, so there is no YAML library: read() understands only the shape this one file
has (nested mappings of scalars and `[a, b]` lists, comments, quoted strings). Anything else
raises ValueError, and the page says it can't read the file rather than guess.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

JURISDICTIONS = Path(__file__).resolve().parent.parent / "governance" / "jurisdictions.yml"
JURISDICTIONS_PATH = "governance/jurisdictions.yml"   # for links to GitHub
LIST_KEYS = ("decide", "ratify", "vote_eligible")
KEY_RE = re.compile(r"([A-Za-z0-9_-]+):(?:\s+(.*))?$")


# ---------------------------------------------------------------- reading the file

def strip_comment(line: str) -> str:
    """The line without a `#` comment (one at the start, or after a space, outside quotes)."""
    quote = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def scalar(s: str):
    """A plain or quoted string, a number, a boolean or a `[a, b]` list of plain strings."""
    s = s.strip()
    if s.startswith("["):
        if not s.endswith("]"):
            raise ValueError(f"unclosed list: {s}")
        inner = s[1:-1].strip()
        items = [scalar(x) for x in inner.split(",")] if inner else []
        if any(not isinstance(x, str) or not x for x in items):
            raise ValueError(f"unexpected list: {s}")
        return items
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s[:1] in "\"'{|>&*!-":
        raise ValueError(f"unsupported value: {s}")
    if s in ("true", "false"):
        return s == "true"
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s


def read(text: str) -> dict:
    """The file as nested dicts. Raises ValueError on anything outside its known shape."""
    root: dict = {}
    stack = [(0, root)]    # (indent, mapping)
    pending = None         # (indent, parent, key) of a key whose value is a nested mapping
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise ValueError(f"line {n}: tab indent")
        line = strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        m = KEY_RE.fullmatch(line.strip())
        if not m:
            raise ValueError(f"line {n}: not a `key: value` line")
        if pending:
            p_indent, parent, key = pending
            pending = None
            if indent > p_indent:
                parent[key] = {}
                stack.append((indent, parent[key]))
            else:
                parent[key] = None   # an empty value
        while indent < stack[-1][0]:
            stack.pop()
        if indent != stack[-1][0]:
            raise ValueError(f"line {n}: unexpected indent")
        mapping = stack[-1][1]
        key, value = m.group(1), m.group(2)
        if key in mapping:
            raise ValueError(f"line {n}: duplicate key {key}")
        if value is None or not value.strip():
            pending = (indent, mapping, key)
            mapping[key] = None
        else:
            mapping[key] = scalar(value)
    return root


def domains(doc: dict) -> list[dict]:
    """The domains, in file order, each with its fields checked. Raises ValueError if the
    file doesn't have the shape the page draws."""
    ds = doc.get("domains")
    if not isinstance(ds, dict) or not ds:
        raise ValueError("no domains")
    out = []
    for name, d in ds.items():
        if not isinstance(d, dict):
            raise ValueError(f"domain {name} is not a mapping")
        for k in LIST_KEYS:
            if not isinstance(d.get(k, []), list):
                raise ValueError(f"domain {name}: {k} is not a list")
        if not isinstance(d.get("owner"), str) or not isinstance(d.get("default_shape"), str):
            raise ValueError(f"domain {name}: missing owner or default_shape")
        out.append({"name": name, "description": d.get("description"),
                    "owner": d["owner"], "default_shape": d["default_shape"],
                    "always_one_way": d.get("always_one_way") is True, "note": d.get("note"),
                    **{k: d.get(k) or [] for k in LIST_KEYS}})
    return out


def identity(ref: str, ids: dict) -> dict:
    """`agents.builder` or `humans.owner` as who it names: kind (agent, owner, or other for a
    reference the file doesn't list), short name and login."""
    group, _, name = ref.partition(".")
    login = (ids.get(group) or {}).get(name) if isinstance(ids.get(group), dict) else None
    if group == "agents" and login:
        return {"kind": "agent", "name": name, "login": login}
    if group == "humans" and login:
        return {"kind": "owner", "name": name, "login": login}
    return {"kind": "other", "name": ref, "login": None}


# ---------------------------------------------------------------- model

def build(text: str | None, records: list[dict]) -> dict:
    """The page's model. `records` are governance.build()'s all_records (each with its review
    flag). `error` is set, and nothing else, when the file is missing or unreadable."""
    if text is None:
        return {"error": f"can't read {JURISDICTIONS_PATH}: not found"}
    try:
        doc = read(text)
        ds = domains(doc)
    except ValueError as e:
        return {"error": f"can't read {JURISDICTIONS_PATH}: {e}"}
    ids = doc.get("identities") if isinstance(doc.get("identities"), dict) else {}
    in_force = [r for r in records if r.get("status") == "in-force"]
    rows = []
    for d in ds:
        recs = sorted((r for r in in_force if r.get("domain") == d["name"]), key=lambda r: r["num"])
        rows.append({**d,
                     "owner": identity(d["owner"], ids),
                     **{k: [identity(x, ids) for x in d[k]] for k in LIST_KEYS},
                     "records": [r["id"] for r in recs],
                     "passed": [r["id"] for r in recs if r.get("flag") == "passed"]})
    known = {d["name"] for d in ds}
    elsewhere = sorted({r["domain"] for r in in_force if r.get("domain") not in known})
    return {"error": None, "domains": rows, "quorum": doc.get("quorum"),
            "consent_window": doc.get("consent_window"), "elsewhere": elsewhere}


# ---------------------------------------------------------------- rendering

def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def who(i: dict) -> str:
    title = f' title="{esc(i["login"])}"' if i["login"] else ""
    return f'<span class="w-{i["kind"]}"{title}>{esc(i["name"])}</span>'


def whos(items: list[dict], empty: str) -> str:
    return ", ".join(who(i) for i in items) if items else f'<span class="muted">{esc(empty)}</span>'


def records_cell(d: dict) -> str:
    if not d["records"]:
        return '<span class="muted">none</span>'
    n = len(d["records"])
    out = f'<a href="decisions.html">{n} in force</a><br><span class="muted">{esc(", ".join(d["records"]))}</span>'
    if d["passed"]:
        out += (f'<br><span class="muted">review date passed: {esc(", ".join(d["passed"]))}'
                "</span>")
    return out


def render(a: dict, repo: str) -> str:
    """The page body."""
    src = f'<a href="https://github.com/{esc(repo)}/blob/main/{JURISDICTIONS_PATH}">{JURISDICTIONS_PATH}</a>'
    out = ["<h1>Authority map</h1>"]
    if a.get("error"):
        out.append(f'<p class="muted">{esc(a["error"])}</p>')
        return "\n".join(out)
    out.append(f'<p class="muted">Who may decide what, from {src}. '
               '<span class="w-agent">Agents</span> in blue, the <span class="w-owner">owner</span> '
               "in amber. Agents decide only two-way choices in their domains (GOVERNANCE.md §3); "
               "everything else is a <code>gov:question</code>. "
               f"Votes need a quorum of {esc(a['quorum'])} of those eligible; the consent window "
               f"is {esc(a['consent_window'])}.</p>")
    rows = []
    for d in a["domains"]:
        flags = ' <span class="pill s-stopped">always one-way</span>' if d["always_one_way"] else ""
        notes = "".join(f'<br><span class="muted">{esc(t)}</span>'
                        for t in (d["description"], d["note"]) if t)
        rows.append(f'<tr id="{esc(d["name"])}"><td><b>{esc(d["name"])}</b>{flags}{notes}</td>'
                    f'<td>{whos(d["decide"], "nobody: ask")}</td><td>{who(d["owner"])}</td>'
                    f'<td>{whos(d["ratify"], "nobody")}</td>'
                    f'<td>{whos(d["vote_eligible"], "—")}</td>'
                    f'<td>{esc(d["default_shape"])}</td><td>{records_cell(d)}</td></tr>')
    out.append('<div class="scroll"><table class="authority"><tr><th>Domain</th><th>Decides</th>'
               "<th>Owner</th><th>Ratify</th><th>Vote-eligible</th><th>Default shape</th>"
               f'<th>Records</th></tr>{"".join(rows)}</table></div>')
    if a["elsewhere"]:
        out.append(f'<p class="muted">In-force records in domains the file doesn\'t list: '
                   f'{esc(", ".join(a["elsewhere"]))}.</p>')
    out.append('<p class="muted">Records count as precedent only while in force and before '
               'their review-by date (GOVERNANCE.md §6). The full log is on '
               '<a href="decisions.html">Decisions</a>.</p>')
    return "\n".join(out)
