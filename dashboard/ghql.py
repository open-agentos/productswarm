"""Batched GraphQL reads for the dashboard (#392).

One REST call per issue or PR made a rebuild cost well over 100 calls and ran the
workflow's token out of its hourly allowance. A GraphQL query can read many issues or PRs
at once through aliases (`i12: issue(number: 12) { ... }`) for about one rate-limit point.
Callers turn the results back into the REST shapes the rest of the page already reads.
Stdlib only.
"""
from __future__ import annotations

import json
import subprocess

QUERY = "query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { %s } }"


def login(author: dict | None) -> str:
    """REST's login. GraphQL names an App `slug` (a Bot), REST `slug[bot]`. A user can't have
    `[bot]` in their login, so only a real App ever gets the suffix."""
    if not author:
        return ""
    return author["login"] + "[bot]" if author.get("__typename") == "Bot" else author["login"]


def batched(repo: str, numbers: list[int], field: str, size: int) -> dict[int, dict | None]:
    """`field % (n, n)` for each number, `size` per query. Returns each number's alias data,
    or None where the query didn't return it, so the caller can fall back to REST for that
    one. `gh` exits 1 when any alias errors (say, a number that isn't a PR), but the others'
    data still comes back, so it's kept; a query with no data at all raises."""
    owner, name = repo.split("/", 1)
    out: dict[int, dict | None] = {}
    for i in range(0, len(numbers), size):
        chunk = numbers[i:i + size]
        q = QUERY % " ".join(field % (n, n) for n in chunk)
        r = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}", "-f", f"owner={owner}",
                            "-f", f"name={name}"], capture_output=True, text=True, timeout=120)
        try:
            found = (json.loads(r.stdout or "null") or {}).get("data", {}).get("repository")
        except (ValueError, AttributeError):
            found = None
        if found is None:
            raise RuntimeError(f"gh api graphql failed: {r.stderr.strip()[:300]}")
        for n in chunk:
            out[n] = found.get(f"{field.split(':', 1)[0] % n}")
    return out


def complete(conn: dict | None) -> list[dict] | None:
    """A connection's nodes if it holds all of them (first: 100 reached the end), else None."""
    if not conn or conn.get("totalCount", 0) > len(conn.get("nodes") or []):
        return None
    return conn["nodes"]
