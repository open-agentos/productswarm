"""Load and validate the swarm manifest (swarm.toml at the repo root).

Python stdlib only (tomllib, 3.11+). Format and location per the owner's answer on #44.

    python3 launcher/manifest.py [PATH]   # print the sessions it would start, or the problems

load() returns one Session per session to start: a [[session]] table with count = 2
gives two Sessions, numbered 1 and 2 within the role. Every problem in the file is
collected and raised together in one ManifestError. load_all(), for `swarm watch` (#487),
instead returns the Sessions from the valid entries with the problems in the rest, so one
bad entry doesn't stop every role; it still raises if the [watch] table is bad.

An optional [watch] table holds the limits for `swarm watch` (v2, #90), per the owner's
answer on #88, GOV-0010: interval_minutes and max_live, both required if the table is there.
max_turns (#147, GOV-0012) is the turn ceiling for the headless runs swarm watch starts: a
positive whole number. It may be left out here, so `swarm up` still works, but `swarm watch`
then refuses to start anything. review_in_actions (#216, GOV-0019) is an optional true or
false, default false: when true, `swarm watch` leaves every [review] trigger to the GitHub
Actions reviewer and starts nothing for it. actions_max_reviews (#257) is the most PRs one
`actions_review.py plan` lists: a whole number of at least 1, optional; with it left out,
plan lists nothing. stale_minutes (#488) is how long a session may sit idle on an issue
before `swarm watch` calls the trigger it holds stale and names the `swarm stop` that
frees it: a whole number of at least 1, optional, default 60. call_ins (#520, GOV-0023) is
an optional true or false, default false: when true, `swarm watch` starts the roles a
`Call in:` line names on a `ready` issue. daily (#588, GOV-0029) is an optional true or
false, default false: when true, `swarm watch` starts the planner on report_issue (a whole
number of at least 1) once each working day at or after daily_at (local time, "HH:MM").
daily = true without both of them is an error; either may be set while daily is off.
asks (#590, GOV-0029) is an optional true or false, default false: when true, `swarm
watch` starts the role an owner's `Ask: <role>: <question>` comment on report_issue names;
asks = true without report_issue is an error. research (#591, GOV-0029) is an optional true
or false, default false: when true, `swarm watch` starts the analyst on an open issue where
the owner or the planner posts `Research: <question>`. load_watch() returns them, or None if
the manifest has no [watch] table.

An optional [merger] table (#589, GOV-0027) is allowed here but read only by merger.py,
which treats a missing or bad one as `off`; this module doesn't check it.
"""
from __future__ import annotations

import sys
import datetime as dt
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "swarm.toml"

DAILY_AT_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
REQUIRED = ("role", "count", "model")
OPTIONAL = ("spend_cap_usd",)
WATCH_KEYS = ("interval_minutes", "max_live")     # required in [watch]
WATCH_OPTIONAL = ("max_turns", "review_in_actions", "actions_max_reviews", "stale_minutes",
                  "call_ins", "daily", "daily_at", "report_issue", "asks",
                  "research")   # watch refuses to start without max_turns


class ManifestError(ValueError):
    """The manifest is missing, unreadable or invalid. str() lists every problem."""

    def __init__(self, path: Path, problems: list[str]):
        self.path = path
        self.problems = problems
        super().__init__(f"{path}: " + "; ".join(problems) if len(problems) == 1
                         else f"{path}:\n" + "\n".join(f"  - {p}" for p in problems))


@dataclass(frozen=True)
class Session:
    role: str
    index: int              # 1-based, within the role
    model: str
    spend_cap_usd: float | None = None

    @property
    def name(self) -> str:
        return f"{self.role}-{self.index}"


@dataclass(frozen=True)
class WatchLimits:
    """How `swarm watch` is limited (GOV-0010). Changing the limits is a `spend` decision;
    changing review_in_actions is a `ci-and-workflows` one (GOV-0019)."""
    interval_minutes: float     # how often it reads GitHub and heartbeat state
    max_live: int               # most live sessions it may have started at once
    max_turns: int | None = None    # --max-turns for each headless run (GOV-0012); None: watch refuses
    review_in_actions: bool = False  # leave [review] to the Actions reviewer (GOV-0019)
    actions_max_reviews: int | None = None  # most PRs one Actions plan lists (#257); None: none
    stale_minutes: int = 60     # idle this long on an issue, a holder is called stale (#488)
    call_ins: bool = False      # start the roles a `Call in:` line names (#520, GOV-0023)
    daily: bool = False         # start the planner's daily report (#588, GOV-0029)
    daily_at: dt.time | None = None     # local time it is due each working day
    report_issue: int | None = None     # the pinned report issue it runs on
    asks: bool = False          # start the role an owner's `Ask:` names (#590, GOV-0029)
    research: bool = False      # start the analyst on a `Research:` line (#591, GOV-0029)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_entry(i: int, entry, roles_dir: Path, seen: dict[str, int]) -> list[str]:
    where = f"session {i}"
    if not isinstance(entry, dict):
        return [f"{where}: must be a [[session]] table"]
    role = entry.get("role")
    if isinstance(role, str) and role:
        where = f"session {i} ({role})"
    problems = []
    for key in sorted(set(entry) - set(REQUIRED) - set(OPTIONAL)):
        problems.append(f"{where}: unknown key '{key}' (allowed: {', '.join(REQUIRED + OPTIONAL)})")
    for key in REQUIRED:
        if key not in entry:
            problems.append(f"{where}: missing '{key}'")

    if "role" in entry:
        if not isinstance(role, str) or not role:
            problems.append(f"{where}: role must be a non-empty string")
        elif "/" in role or role.startswith(".") or not (roles_dir / f"{role}.md").is_file():
            problems.append(f"{where}: unknown role '{role}' (no roles/{role}.md)")
        elif role in seen:
            problems.append(f"{where}: role '{role}' already listed in session {seen[role]}; "
                            f"use count instead")
        else:
            seen[role] = i
    if "count" in entry:
        count = entry["count"]
        if not isinstance(count, int) or isinstance(count, bool):
            problems.append(f"{where}: count must be a whole number, got {count!r}")
        elif count < 1:
            problems.append(f"{where}: count must be at least 1, got {count}")
    if "model" in entry:
        model = entry["model"]
        if not isinstance(model, str) or not model.strip():
            problems.append(f"{where}: model must be a non-empty string")
    if "spend_cap_usd" in entry:
        cap = entry["spend_cap_usd"]
        if not _is_number(cap) or not cap > 0 or cap == float("inf"):
            problems.append(f"{where}: spend_cap_usd must be a positive number, got {cap!r}")
    return problems


def _check_watch(table) -> list[str]:
    if not isinstance(table, dict):
        return ["watch: must be a [watch] table"]
    allowed = WATCH_KEYS + WATCH_OPTIONAL
    problems = [f"watch: unknown key '{k}' (allowed: {', '.join(allowed)})"
                for k in sorted(set(table) - set(allowed))]
    problems += [f"watch: missing '{k}'" for k in WATCH_KEYS if k not in table]
    if "interval_minutes" in table:
        v = table["interval_minutes"]
        if not _is_number(v) or not v > 0 or v == float("inf"):
            problems.append(f"watch: interval_minutes must be a positive number, got {v!r}")
    if "max_live" in table:
        v = table["max_live"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            problems.append(f"watch: max_live must be a whole number of at least 1, got {v!r}")
    if "max_turns" in table:
        v = table["max_turns"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            problems.append(f"watch: max_turns must be a whole number of at least 1, got {v!r}")
    if "actions_max_reviews" in table:
        v = table["actions_max_reviews"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            problems.append(f"watch: actions_max_reviews must be a whole number of at least 1, got {v!r}")
    if "stale_minutes" in table:
        v = table["stale_minutes"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            problems.append(f"watch: stale_minutes must be a whole number of at least 1, got {v!r}")
    for key in ("review_in_actions", "call_ins", "daily", "asks", "research"):
        if key in table and not isinstance(table[key], bool):
            problems.append(f"watch: {key} must be true or false, got {table[key]!r}")
    if "daily_at" in table:
        v = table["daily_at"]
        if not isinstance(v, str) or not DAILY_AT_RE.match(v):
            problems.append(f"watch: daily_at must be a local time as \"HH:MM\" (24-hour), got {v!r}")
    if "report_issue" in table:
        v = table["report_issue"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            problems.append(f"watch: report_issue must be an issue number, got {v!r}")
    if table.get("daily") is True:
        problems += [f"watch: daily = true needs '{k}'" for k in ("daily_at", "report_issue")
                     if k not in table]
    if table.get("asks") is True and "report_issue" not in table:
        problems.append("watch: asks = true needs 'report_issue'")
    return problems


def parse(text: str, path: Path = DEFAULT_PATH, roles_dir: Path = ROOT / "roles") -> list[Session]:
    """Validate manifest text and expand it into sessions. Raises ManifestError."""
    return parse_all(text, path, roles_dir)[0]


def parse_all(text: str, path: Path = DEFAULT_PATH, roles_dir: Path = ROOT / "roles"
              ) -> tuple[list[Session], WatchLimits | None]:
    """Validate manifest text: its sessions, and its [watch] limits or None. Raises
    ManifestError on any problem, in a [[session]] entry or not."""
    sessions, limits, problems = parse_valid(text, path, roles_dir)
    if problems:
        raise ManifestError(path, problems)
    return sessions, limits


def parse_valid(text: str, path: Path = DEFAULT_PATH, roles_dir: Path = ROOT / "roles"
                ) -> tuple[list[Session], WatchLimits | None, list[str]]:
    """Manifest text as (sessions from the valid [[session]] entries, [watch] limits or None,
    the problems with the rest) (#487): one bad entry doesn't stop the others. Raises
    ManifestError only when nothing can be trusted: the text isn't TOML, or the [watch]
    table is bad (GOV-0010, GOV-0012); its problems then list every other problem too."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(path, [f"not valid TOML: {e}"]) from None

    problems = [f"unknown top-level key '{k}' (only [[session]] tables, [watch] and [merger] "
                "are allowed)" for k in sorted(set(data) - {"session", "watch", "merger"})]
    watch_problems = _check_watch(data["watch"]) if "watch" in data else []
    problems += watch_problems
    entries = data.get("session")
    if entries is None:
        problems.append("no [[session]] tables")
        entries = []
    elif not isinstance(entries, list):
        problems.append("'session' must be [[session]] tables")
        entries = []
    elif not entries:
        problems.append("no [[session]] tables")

    seen: dict[str, int] = {}
    valid = []
    for i, entry in enumerate(entries, 1):
        bad = _check_entry(i, entry, roles_dir, seen)
        problems += bad
        if not bad:
            valid.append(entry)
    if watch_problems:
        raise ManifestError(path, problems)

    sessions = []
    for entry in valid:
        cap = entry.get("spend_cap_usd")
        for n in range(1, entry["count"] + 1):
            sessions.append(Session(role=entry["role"], index=n, model=entry["model"].strip(),
                                    spend_cap_usd=None if cap is None else float(cap)))
    w = data.get("watch")
    limits = None if w is None else WatchLimits(float(w["interval_minutes"]), w["max_live"],
                                                w.get("max_turns"), w.get("review_in_actions", False),
                                                w.get("actions_max_reviews"), w.get("stale_minutes", 60),
                                                w.get("call_ins", False), w.get("daily", False),
                                                _time(w.get("daily_at")), w.get("report_issue"),
                                                w.get("asks", False), w.get("research", False))
    return sessions, limits, problems


def _time(v: str | None) -> dt.time | None:
    if v is None:
        return None
    h, m = DAILY_AT_RE.match(v).groups()
    return dt.time(int(h), int(m))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError(path, ["file not found"]) from None
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(path, [f"can't read it: {e}"]) from None


def _roles_dir(roles_dir: Path | str | None) -> Path:
    return Path(roles_dir) if roles_dir is not None else ROOT / "roles"


def load(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None) -> list[Session]:
    """Read and validate a manifest file. Roles are checked against roles/ next to the
    repo root unless roles_dir is given. Raises ManifestError on any problem."""
    path = Path(path)
    return parse_all(_read(path), path, _roles_dir(roles_dir))[0]


def load_watch(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None) -> WatchLimits | None:
    """The manifest's [watch] limits, or None if it has none. A bad [[session]] entry
    doesn't stop it (#487). Raises ManifestError if the file can't be read, isn't TOML,
    or its [watch] table is bad."""
    return load_all(path, roles_dir)[1]


def load_all(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None
             ) -> tuple[list[Session], WatchLimits | None, list[str]]:
    """Read a manifest file: (sessions from its valid entries, [watch] limits or None, the
    problems with the rest), as parse_valid(). Raises ManifestError if the file can't be
    read, isn't TOML, or its [watch] table is bad."""
    path = Path(path)
    return parse_valid(_read(path), path, _roles_dir(roles_dir))


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    try:
        sessions, limits = parse_all(_read(path), path, ROOT / "roles")
    except ManifestError as e:
        print(f"swarm manifest: {e}", file=sys.stderr)
        return 1
    for s in sessions:
        cap = "no cap" if s.spend_cap_usd is None else f"cap ${s.spend_cap_usd:,.2f}"
        print(f"{s.name}\t{s.model}\t{cap}")
    if limits:
        turns = "no max_turns" if limits.max_turns is None else f"max {limits.max_turns} turns a run"
        planned = ("no actions_max_reviews" if limits.actions_max_reviews is None
                   else f"at most {limits.actions_max_reviews} Actions reviews a sweep")
        reviews = "[review] left to Actions" if limits.review_in_actions else "[review] local"
        calls = "call-ins on" if limits.call_ins else "call-ins off"
        daily = (f"[daily] on #{limits.report_issue} at {limits.daily_at:%H:%M}" if limits.daily
                 else "[daily] off")
        asks = f"[ask] on #{limits.report_issue}" if limits.asks else "[ask] off"
        research = "[research] on" if limits.research else "[research] off"
        print(f"watch\tevery {limits.interval_minutes:g} min\tat most {limits.max_live} live\t{turns}"
              f"\t{planned}\t{reviews}\t{calls}\t{daily}\t{asks}\t{research}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
