"""Label sets and labelled sets: the two file formats the classifier engine reads (#1010).

    classify/labelsets/<name>.yml   the labels, optional flags, the agreement threshold, the
                                    call cap and the pass mark
    classify/data/<name>.jsonl      one labelled item per line

Both are described in classify/README.md. load_labelset() and load_items() validate
everything they read and raise FormatError listing every problem, so an eval never runs on a
half-understood file.

Standard library only, so there is no YAML library: read_yaml() understands only the subset a
label set needs (nested mappings, block lists of scalars or mappings, `[a, b]` flow lists,
plain or quoted scalars, numbers, booleans, comments). Anything else raises FormatError
rather than being guessed at, as dashboard/authority.py does for jurisdictions.yml.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

NEEDS_HUMAN = "needs human"
DRAFT = "draft"   # labelled_by for a model's draft label: never gold, never scored
SPLITS = ("dev", "test")
KEY_RE = re.compile(r"([A-Za-z0-9_-]+):(?:\s+(.*))?$")


class FormatError(ValueError):
    """A label set or labelled set that can't be trusted; str() lists every problem."""

    def __init__(self, path, problems: list[str]):
        self.path = path
        self.problems = problems
        super().__init__(f"{path}: " + "; ".join(problems))


# ---------------------------------------------------------------- the YAML subset

def _strip_comment(line: str) -> str:
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


def _split_flow(inner: str) -> list[str]:
    parts, cur, quote = [], "", None
    for c in inner:
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == ",":
            parts.append(cur)
            cur = ""
            continue
        cur += c
    parts.append(cur)
    return parts


def scalar(s: str):
    """A plain or quoted string, a number, a boolean, null, or a `[a, b]` list of scalars."""
    s = s.strip()
    if s.startswith("["):
        if not s.endswith("]"):
            raise ValueError(f"unclosed list: {s}")
        inner = s[1:-1].strip()
        return [scalar(x) for x in _split_flow(inner)] if inner else []
    if s.startswith('"'):
        try:
            v = json.loads(s)
        except json.JSONDecodeError:
            raise ValueError(f"bad double-quoted string: {s}") from None
        if not isinstance(v, str):
            raise ValueError(f"bad double-quoted string: {s}")
        return v
    if s.startswith("'"):
        if len(s) < 2 or not s.endswith("'"):
            raise ValueError(f"unclosed single-quoted string: {s}")
        return s[1:-1].replace("''", "'")
    if s[:1] in "{|>&*!%@`":
        raise ValueError(f"unsupported value: {s}")
    if s in ("true", "false"):
        return s == "true"
    if s in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d*|-?\.\d+", s):
        return float(s)
    return s


def read_yaml(text: str):
    """The value the YAML subset in text describes. Raises ValueError on anything else."""
    lines = []
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError(f"line {n}: tabs in indentation")
        line = _strip_comment(raw)
        if line.strip() in ("", "---"):
            continue
        lines.append([len(line) - len(line.lstrip(" ")), line.strip(), n])
    if not lines:
        return {}
    value, i = _block(lines, 0, lines[0][0])
    if i != len(lines):
        raise ValueError(f"line {lines[i][2]}: unexpected indentation")
    return value


def _block(lines, i, indent):
    if lines[i][1] == "-" or lines[i][1].startswith("- "):
        return _list(lines, i, indent)
    return _mapping(lines, i, indent)


def _child(lines, i, indent, n):
    """The nested block after a `key:` or `-` with nothing after it, deeper than indent."""
    if i >= len(lines) or lines[i][0] <= indent:
        raise ValueError(f"line {n}: nothing nested under it")
    return _block(lines, i, lines[i][0])


def _list(lines, i, indent):
    out = []
    while i < len(lines) and lines[i][0] == indent:
        text, n = lines[i][1], lines[i][2]
        if not (text == "-" or text.startswith("- ")):
            raise ValueError(f"line {n}: expected a list item")
        rest = text[1:].lstrip()
        if not rest:
            value, i = _child(lines, i + 1, indent, n)
        elif KEY_RE.match(rest) and not rest.startswith(("\"", "'")):
            # "- key: value" starts a mapping whose keys sit at the column of "key".
            lines[i] = [indent + (len(text) - len(rest)), rest, n]
            value, i = _mapping(lines, i, lines[i][0])
        else:
            value, i = scalar(rest), i + 1
        out.append(value)
    if i < len(lines) and lines[i][0] > indent:
        raise ValueError(f"line {lines[i][2]}: unexpected indentation")
    return out, i


def _mapping(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        text, n = lines[i][1], lines[i][2]
        m = KEY_RE.match(text)
        if not m or text.startswith("- "):
            raise ValueError(f"line {n}: expected `key: value`")
        key, rest = m.group(1), m.group(2)
        if key in out:
            raise ValueError(f"line {n}: '{key}' appears twice")
        if rest is None or not rest.strip():
            out[key], i = _child(lines, i + 1, indent, n)
        else:
            out[key], i = scalar(rest), i + 1
    if i < len(lines) and lines[i][0] > indent:
        raise ValueError(f"line {lines[i][2]}: unexpected indentation")
    return out, i


# ---------------------------------------------------------------- label sets

@dataclass(frozen=True)
class Label:
    name: str
    definition: str
    boundary: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class Flag:
    name: str
    definition: str


@dataclass(frozen=True)
class PassMark:
    accuracy: float
    coverage: Optional[float] = None
    min_recall: dict = field(default_factory=dict)   # label -> minimum recall


@dataclass(frozen=True)
class LabelSet:
    name: str
    labels: tuple[Label, ...]
    flags: tuple[Flag, ...]
    threshold: float      # majority agreement below this answers "needs human"
    runs: int             # samples per item by default
    max_calls: int        # the most model calls one live run may make
    pass_mark: PassMark
    description: str = ""
    sha: str = ""         # sha256 of the file's bytes, for reports (GOV-0044)

    @property
    def label_names(self) -> list[str]:
        return [lb.name for lb in self.labels]

    @property
    def flag_names(self) -> list[str]:
        return [f.name for f in self.flags]


LABELSET_KEYS = ("description", "labels", "flags", "threshold", "runs", "max_calls", "pass_mark")
LABEL_KEYS = ("name", "definition", "boundary", "examples")
FLAG_KEYS = ("name", "definition")
PASS_KEYS = ("accuracy", "coverage", "min_recall")


def _fraction(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1


def _strings(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def parse_labelset(name: str, text: str, sha: str = "") -> tuple[Optional[LabelSet], list[str]]:
    """(the LabelSet, []) or (None, every problem) for a label set's YAML text."""
    try:
        data = read_yaml(text)
    except ValueError as e:
        return None, [str(e)]
    if not isinstance(data, dict):
        return None, ["must be a mapping of keys"]
    p = [f"unknown key '{k}' (allowed: {', '.join(LABELSET_KEYS)})" for k in data if k not in LABELSET_KEYS]
    for k in ("labels", "threshold", "max_calls", "pass_mark"):
        if k not in data:
            p.append(f"'{k}' is required")

    labels = []
    raw = data.get("labels", [])
    if not isinstance(raw, list):
        p.append("labels: must be a list")
        raw = []
    for i, lb in enumerate(raw, 1):
        where = f"labels[{i}]"
        if not isinstance(lb, dict):
            p.append(f"{where}: must be a mapping")
            continue
        p += [f"{where}: unknown key '{k}' (allowed: {', '.join(LABEL_KEYS)})" for k in lb if k not in LABEL_KEYS]
        if not _text(lb.get("name")) or lb.get("name") == NEEDS_HUMAN:
            p.append(f"{where}: name must be a non-empty string other than '{NEEDS_HUMAN}'")
            continue
        where = f"label '{lb['name']}'"
        if not _text(lb.get("definition")):
            p.append(f"{where}: definition is required")
        if "boundary" in lb and not _strings(lb["boundary"]):
            p.append(f"{where}: boundary must be a list of rules")
        ex = lb.get("examples")
        if not _strings(ex) or not 2 <= len(ex) <= 3:
            p.append(f"{where}: examples must be a list of 2 or 3 examples")
        labels.append(Label(lb["name"], str(lb.get("definition", "")),
                            tuple(lb.get("boundary") or ()) if _strings(lb.get("boundary") or []) else (),
                            tuple(ex) if _strings(ex) else ()))
    names = [lb.name for lb in labels]
    if raw and len(labels) == len(raw) and len(labels) < 2:
        p.append("labels: at least two labels are needed")
    p += [f"label '{n}' appears twice" for n in sorted({n for n in names if names.count(n) > 1})]

    flags = []
    rawf = data.get("flags", [])
    if not isinstance(rawf, list):
        p.append("flags: must be a list")
        rawf = []
    for i, f in enumerate(rawf, 1):
        if not isinstance(f, dict) or not _text(f.get("name")) or not _text(f.get("definition")):
            p.append(f"flags[{i}]: needs a name and a definition")
            continue
        p += [f"flag '{f['name']}': unknown key '{k}'" for k in f if k not in FLAG_KEYS]
        flags.append(Flag(f["name"], f["definition"]))
    fnames = [f.name for f in flags]
    p += [f"flag '{n}' appears twice" for n in sorted({n for n in fnames if fnames.count(n) > 1})]

    threshold = data.get("threshold", 0)
    if "threshold" in data and not _fraction(threshold):
        p.append("threshold: must be a number from 0 to 1")
    runs = data.get("runs", 3)
    if not isinstance(runs, int) or isinstance(runs, bool) or runs < 1:
        p.append("runs: must be a whole number of at least 1")
    max_calls = data.get("max_calls", 0)
    if "max_calls" in data and (not isinstance(max_calls, int) or isinstance(max_calls, bool) or max_calls < 1):
        p.append("max_calls: must be a whole number of at least 1")
    desc = data.get("description", "")
    if not isinstance(desc, str):
        p.append("description: must be a string")

    pm = data.get("pass_mark", {})
    pass_mark = None
    if not isinstance(pm, dict):
        p.append("pass_mark: must be a mapping")
    elif "pass_mark" in data:
        p += [f"pass_mark: unknown key '{k}' (allowed: {', '.join(PASS_KEYS)})" for k in pm if k not in PASS_KEYS]
        if not _fraction(pm.get("accuracy")):
            p.append("pass_mark: accuracy must be a number from 0 to 1")
        if "coverage" in pm and not _fraction(pm["coverage"]):
            p.append("pass_mark: coverage must be a number from 0 to 1")
        mr = pm.get("min_recall", {})
        if not isinstance(mr, dict):
            p.append("pass_mark: min_recall must be a mapping of label to recall")
            mr = {}
        for k, v in mr.items():
            if k not in names:
                p.append(f"pass_mark: min_recall names unknown label '{k}'")
            if not _fraction(v):
                p.append(f"pass_mark: min_recall for '{k}' must be a number from 0 to 1")
        pass_mark = PassMark(pm.get("accuracy", 0), pm.get("coverage"), dict(mr))

    if p:
        return None, p
    return LabelSet(name, tuple(labels), tuple(flags), threshold, runs, max_calls, pass_mark,
                    desc, sha), []


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_labelset(path) -> LabelSet:
    """The label set at path (its name is the file's stem). Raises FormatError."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise FormatError(path, [f"can't read it: {e.strerror or e}"]) from None
    ls, problems = parse_labelset(path.stem, text, sha256(path))
    if problems:
        raise FormatError(path, problems)
    return ls


# ---------------------------------------------------------------- labelled sets

@dataclass(frozen=True)
class Item:
    id: str
    text: str
    label: str            # the gold label
    split: str            # "dev" or "test"
    labelled_by: str
    flags: dict = field(default_factory=dict)   # flag -> bool, gold
    week: Optional[str] = None                  # e.g. "2026-W45", for share error
    hard: Optional[str] = None                  # the boundary rule a hard case tests
    fixes: Optional[int] = None                 # the PR number a fix flag points at


ITEM_KEYS = ("id", "text", "label", "split", "labelled_by", "flags", "week", "hard", "fixes")


def parse_items(text: str, labelset: LabelSet) -> tuple[list[Item], list[str]]:
    """(the items, every problem) from a labelled set's JSON Lines text."""
    items, p, seen = [], [], set()
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        where = f"line {n}"
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            p.append(f"{where}: not JSON ({e.msg})")
            continue
        if not isinstance(d, dict):
            p.append(f"{where}: must be a JSON object")
            continue
        bad = [f"{where}: unknown key '{k}' (allowed: {', '.join(ITEM_KEYS)})" for k in d if k not in ITEM_KEYS]
        for k in ("id", "text", "label", "split", "labelled_by"):
            if not _text(d.get(k)):
                bad.append(f"{where}: '{k}' must be a non-empty string")
        if _text(d.get("label")) and d["label"] not in labelset.label_names:
            bad.append(f"{where}: label '{d['label']}' isn't in the label set")
        if _text(d.get("split")) and d["split"] not in SPLITS:
            bad.append(f"{where}: split must be dev or test")
        flags = d.get("flags", {})
        if not isinstance(flags, dict) or not all(isinstance(v, bool) for v in flags.values()):
            bad.append(f"{where}: flags must map flag names to true or false")
            flags = {}
        bad += [f"{where}: flag '{k}' isn't in the label set" for k in flags if k not in labelset.flag_names]
        if "week" in d and not _text(d["week"]):
            bad.append(f"{where}: week must be a non-empty string")
        if "hard" in d and not _text(d["hard"]):
            bad.append(f"{where}: hard must be the name of a boundary rule")
        if "fixes" in d and (not isinstance(d["fixes"], int) or isinstance(d["fixes"], bool)
                             or d["fixes"] < 1):
            bad.append(f"{where}: fixes must be a PR number")
        if _text(d.get("id")):
            if d["id"] in seen:
                bad.append(f"{where}: id '{d['id']}' appears twice")
            seen.add(d["id"])
        if bad:
            p += bad
            continue
        items.append(Item(d["id"], d["text"], d["label"], d["split"], d["labelled_by"], dict(flags),
                          d.get("week"), d.get("hard"), d.get("fixes")))
    return items, p


def load_items(path, labelset: LabelSet) -> list[Item]:
    """Every item in the labelled set at path. Raises FormatError."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise FormatError(path, [f"can't read it: {e.strerror or e}"]) from None
    items, problems = parse_items(text, labelset)
    if problems:
        raise FormatError(path, problems)
    return items
