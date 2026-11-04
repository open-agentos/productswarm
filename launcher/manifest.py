"""Load and validate the swarm manifest (swarm.toml at the repo root).

Python stdlib only (tomllib, 3.11+). Format and location per the owner's answer on #44.

    python3 launcher/manifest.py [PATH]   # print the sessions it would start, or the problems

load() returns one Session per session to start: a [[session]] table with count = 2
gives two Sessions, numbered 1 and 2 within the role. Every problem in the file is
collected and raised together in one ManifestError.

An optional [watch] table holds the limits for `swarm watch` (v2, #90), per the owner's
answer on #88, GOV-0010: interval_minutes and max_live, both required if the table is there.
max_turns (#147, GOV-0012) is the turn ceiling for the headless runs swarm watch starts: a
positive whole number. It may be left out here, so `swarm up` still works, but `swarm watch`
then refuses to start anything. review_in_actions (#216, GOV-0019) is an optional true or
false, default false: when true, `swarm watch` leaves every [review] trigger to the GitHub
Actions reviewer and starts nothing for it. actions_max_reviews (#257) is the most PRs one
`actions_review.py plan` lists: a whole number of at least 1, optional; with it left out,
plan lists nothing. load_watch() returns them, or None if the
manifest has no [watch] table.
"""
from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "swarm.toml"

REQUIRED = ("role", "count", "model")
OPTIONAL = ("spend_cap_usd",)
WATCH_KEYS = ("interval_minutes", "max_live")     # required in [watch]
WATCH_OPTIONAL = ("max_turns", "review_in_actions", "actions_max_reviews")   # watch refuses to start without max_turns


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
    if "review_in_actions" in table:
        v = table["review_in_actions"]
        if not isinstance(v, bool):
            problems.append(f"watch: review_in_actions must be true or false, got {v!r}")
    return problems


def parse(text: str, path: Path = DEFAULT_PATH, roles_dir: Path = ROOT / "roles") -> list[Session]:
    """Validate manifest text and expand it into sessions. Raises ManifestError."""
    return parse_all(text, path, roles_dir)[0]


def parse_all(text: str, path: Path = DEFAULT_PATH, roles_dir: Path = ROOT / "roles"
              ) -> tuple[list[Session], WatchLimits | None]:
    """Validate manifest text: its sessions, and its [watch] limits or None. Raises ManifestError."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(path, [f"not valid TOML: {e}"]) from None

    problems = [f"unknown top-level key '{k}' (only [[session]] tables and [watch] are allowed)"
                for k in sorted(set(data) - {"session", "watch"})]
    if "watch" in data:
        problems += _check_watch(data["watch"])
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
    for i, entry in enumerate(entries, 1):
        problems += _check_entry(i, entry, roles_dir, seen)
    if problems:
        raise ManifestError(path, problems)

    sessions = []
    for entry in entries:
        cap = entry.get("spend_cap_usd")
        for n in range(1, entry["count"] + 1):
            sessions.append(Session(role=entry["role"], index=n, model=entry["model"].strip(),
                                    spend_cap_usd=None if cap is None else float(cap)))
    w = data.get("watch")
    limits = None if w is None else WatchLimits(float(w["interval_minutes"]), w["max_live"],
                                                w.get("max_turns"), w.get("review_in_actions", False),
                                                w.get("actions_max_reviews"))
    return sessions, limits


def load(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None) -> list[Session]:
    """Read and validate a manifest file. Roles are checked against roles/ next to the
    repo root unless roles_dir is given. Raises ManifestError."""
    return load_all(path, roles_dir)[0]


def load_watch(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None) -> WatchLimits | None:
    """The manifest's [watch] limits, or None if it has none. Raises ManifestError."""
    return load_all(path, roles_dir)[1]


def load_all(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None
             ) -> tuple[list[Session], WatchLimits | None]:
    """Read and validate a manifest file: (sessions, [watch] limits or None). Raises ManifestError."""
    path = Path(path)
    roles_dir = Path(roles_dir) if roles_dir is not None else ROOT / "roles"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError(path, ["file not found"]) from None
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(path, [f"can't read it: {e}"]) from None
    return parse_all(text, path, roles_dir)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    try:
        sessions, limits = load_all(path)
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
        print(f"watch\tevery {limits.interval_minutes:g} min\tat most {limits.max_live} live\t{turns}"
              f"\t{planned}\t{reviews}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
