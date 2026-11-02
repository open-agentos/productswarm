"""Load and validate the swarm manifest (swarm.toml at the repo root).

Python stdlib only (tomllib, 3.11+). Format and location per the owner's answer on #44.

    python3 launcher/manifest.py [PATH]   # print the sessions it would start, or the problems

load() returns one Session per session to start: a [[session]] table with count = 2
gives two Sessions, numbered 1 and 2 within the role. Every problem in the file is
collected and raised together in one ManifestError.
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


def parse(text: str, path: Path = DEFAULT_PATH, roles_dir: Path = ROOT / "roles") -> list[Session]:
    """Validate manifest text and expand it into sessions. Raises ManifestError."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(path, [f"not valid TOML: {e}"]) from None

    problems = [f"unknown top-level key '{k}' (only [[session]] tables are allowed)"
                for k in sorted(set(data) - {"session"})]
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
    return sessions


def load(path: Path | str = DEFAULT_PATH, roles_dir: Path | str | None = None) -> list[Session]:
    """Read and validate a manifest file. Roles are checked against roles/ next to the
    repo root unless roles_dir is given. Raises ManifestError."""
    path = Path(path)
    roles_dir = Path(roles_dir) if roles_dir is not None else ROOT / "roles"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError(path, ["file not found"]) from None
    except (OSError, UnicodeDecodeError) as e:
        raise ManifestError(path, [f"can't read it: {e}"]) from None
    return parse(text, path, roles_dir)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PATH
    try:
        sessions = load(path)
    except ManifestError as e:
        print(f"swarm manifest: {e}", file=sys.stderr)
        return 1
    for s in sessions:
        cap = "no cap" if s.spend_cap_usd is None else f"cap ${s.spend_cap_usd:,.2f}"
        print(f"{s.name}\t{s.model}\t{cap}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
