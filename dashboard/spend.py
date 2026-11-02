"""Rough spend for the dashboard: API list-price equivalent of each session's tokens.

Method (the default in gov question #28, pending a ruling):
  - cost = cumulative token_counts × the model's list price per million tokens;
  - cache writes are priced at the 1-hour rate (Claude Code sessions use the 1-hour
    cache; the heartbeat records one cache-creation total, not a split by TTL);
  - a non-null `cost_usd` on an event wins over the estimate;
  - an unknown model or missing token counts gives no figure, and the session is
    left out of totals.

It is what the tokens would cost at API list price, not what was billed: sessions
on a subscription aren't charged per token.
"""
from __future__ import annotations

import datetime as dt
import re

# $ per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing
PRICES_AS_OF = "2026-11-02"
PRICES = {
    #                    input   1h cache write  cache read  output
    "claude-fable-5-1":  (10.00, 20.00, 0.25, 50.00),
    "claude-mythos-5-1": (10.00, 20.00, 0.25, 50.00),
    "claude-fable-5":    (10.00, 20.00, 1.00, 50.00),
    "claude-mythos-5":   (10.00, 20.00, 1.00, 50.00),
    "claude-opus-5-5":   (4.00, 8.00, 0.20, 20.00),
    "claude-opus-5":     (5.00, 10.00, 0.50, 25.00),
    "claude-opus-4-8":   (5.00, 10.00, 0.50, 25.00),
    "claude-opus-4-7":   (5.00, 10.00, 0.50, 25.00),
    "claude-opus-4-6":   (5.00, 10.00, 0.50, 25.00),
    "claude-opus-4-5":   (5.00, 10.00, 0.50, 25.00),
    "claude-sonnet-5-5": (2.00, 4.00, 0.10, 10.00),
    "claude-sonnet-5":   (2.00, 4.00, 0.20, 10.00),
    "claude-sonnet-4-6": (3.00, 6.00, 0.30, 15.00),
    "claude-sonnet-4-5": (3.00, 6.00, 0.30, 15.00),
    # Haiku 5.5 costs more for prompts over 100K tokens; per-request size isn't recorded.
    "claude-haiku-5-5":  (0.10, 0.20, 0.01, 0.50),
    "claude-haiku-4-5":  (1.00, 2.00, 0.10, 5.00),
}
METHOD = (f"API list-price equivalent: each session's token counts × the model's list price "
          f"(prices as of {PRICES_AS_OF}; cache writes at the 1-hour rate). "
          f"Not what was billed; sessions on a subscription aren't charged per token.")

SUFFIX_RE = re.compile(r"(\[[^\]]*\]|-\d{8}|@\d{8})$")  # "[1m]", date snapshots


def rates(model: str | None) -> tuple | None:
    m = (model or "").strip().lower()
    for _ in range(2):
        m = SUFFIX_RE.sub("", m)
    return PRICES.get(m)


def event_cost(ev: dict) -> float | None:
    """Cumulative session cost as of this event, or None if it can't be told."""
    if isinstance(ev.get("cost_usd"), (int, float)):
        return float(ev["cost_usd"])
    t, r = ev.get("token_counts"), rates(ev.get("model"))
    if not isinstance(t, dict) or r is None:
        return None
    try:
        tokens = (t["input"], t["cache_creation"], t["cache_read"], t["output"])
    except KeyError:
        return None
    return sum(n * price for n, price in zip(tokens, r)) / 1_000_000


def session_cost(events: list[dict]) -> float | None:
    """Latest known cumulative cost (events oldest first)."""
    return next((c for c in map(event_cost, reversed(events)) if c is not None), None)


def daily(events: list[dict], parse_ts) -> dict[dt.date, float]:
    """A session's cost increase per UTC day (events oldest first)."""
    out: dict[dt.date, float] = {}
    prev = 0.0
    for ev in events:
        c = event_cost(ev)
        if c is None:
            continue
        day = parse_ts(ev["ts"]).astimezone(dt.timezone.utc).date()
        # Cumulative counts shouldn't fall; if they do (a restart), count nothing.
        out[day] = out.get(day, 0.0) + max(0.0, c - prev)
        prev = max(prev, c)
    return out


def usd(x: float | None) -> str:
    if x is None:
        return "—"
    return f"${x:,.2f}" if x >= 0.995 or x == 0 else f"${x:.2f}" if x >= 0.01 else "<$0.01"
