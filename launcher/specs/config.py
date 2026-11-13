"""The specs bridge's `[specs]` table in swarm.toml, and the backend it picks (#952, #942).

    [specs]
    backend = "fake"                 # "notion", "fake" or "productboard"
    parent_page = "<page id>"        # Notion's parent page; unused by fake
    fixture = "specs/fixture.json"   # the fake backend's state file

load() reads the table and source() turns it into a SpecSource, so no `swarm specs`
command builds a backend itself. launcher/manifest.py only checks that `[specs]` is a
table; this module validates what is in it, as merger.py does for `[merger]`.

A relative `fixture` is read from the directory swarm.toml is in. No token is read here or
from swarm.toml: the Notion token is read only by NotionSource, from its own file (#951,
GOV-0043). The notion backend is wired in by #1007. Standard library only.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

BACKENDS = ("notion", "fake", "productboard")
KEYS = ("backend", "parent_page", "fixture")


class SpecsConfigError(ValueError):
    """The [specs] table is bad, or names a backend that can't be built."""


@dataclass(frozen=True)
class SpecsConfig:
    backend: str                        # one of BACKENDS
    parent_page: Optional[str] = None   # Notion's parent page id; unused by fake
    fixture: Optional[Path] = None      # the fake backend's state file


def load(path: Union[str, Path]) -> Optional[SpecsConfig]:
    """[specs] from the swarm.toml at path, or None if it has no [specs] table. Raises
    SpecsConfigError if the file can't be read, isn't TOML, or the table is bad."""
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise SpecsConfigError(f"{path}: can't read it: {e}") from None
    except tomllib.TOMLDecodeError as e:
        raise SpecsConfigError(f"{path}: not valid TOML: {e}") from None
    if "specs" not in data:
        return None
    t = data["specs"]
    if not isinstance(t, dict):
        raise SpecsConfigError("specs: must be a [specs] table")
    unknown = sorted(set(t) - set(KEYS))
    if unknown:
        raise SpecsConfigError(f"specs: unknown key '{unknown[0]}' (allowed: {', '.join(KEYS)})")
    backend = t.get("backend")
    if backend is None:
        raise SpecsConfigError(f"specs: missing 'backend' (one of {', '.join(BACKENDS)})")
    if backend not in BACKENDS:
        raise SpecsConfigError(f"specs: unknown backend {backend!r} (one of {', '.join(BACKENDS)})")
    for key in ("parent_page", "fixture"):
        v = t.get(key)
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise SpecsConfigError(f"specs: {key} must be a non-empty string, got {v!r}")
    fixture = t.get("fixture")
    return SpecsConfig(backend, t.get("parent_page"),
                       None if fixture is None else path.parent / fixture)


def source(cfg: SpecsConfig):
    """The SpecSource cfg names. Raises SpecsConfigError for a backend that isn't built yet,
    a fake backend with no fixture, a notion backend with no parent_page, or a Notion token
    file that is missing or not private (its message never holds the token). FakeSource's
    own errors pass through."""
    if cfg.backend == "fake":
        if cfg.fixture is None:
            raise SpecsConfigError("specs: backend \"fake\" needs 'fixture'")
        from .fake import FakeSource
        return FakeSource(cfg.fixture)
    if cfg.backend == "notion":
        if cfg.parent_page is None:
            raise SpecsConfigError("specs: backend \"notion\" needs 'parent_page'")
        from .notion import NotionSource, TokenError
        try:
            # NotionSource reads the token itself, from its own file (GOV-0043), here and
            # before any request; a missing or open file stops the command on one line.
            return NotionSource(cfg.parent_page)
        except TokenError as e:
            raise SpecsConfigError(f"specs: {e}") from None
    if cfg.backend == "productboard":
        raise SpecsConfigError("specs: backend \"productboard\" is not built yet "
                               "(a stub until an account exists, #937 §7)")
    raise SpecsConfigError(f"specs: unknown backend {cfg.backend!r} (one of {', '.join(BACKENDS)})")
