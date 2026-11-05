"""The desk's "What the numbers say" (#406): each trend is a sentence and a sparkline.

Sentences are templates filled from numbers (#397), never written by a model, and carry a
direction word ("up from", "down from") only when both weeks have enough data to compare.
Below MIN_COUNT the sentence says "too few to tell" instead of a number.

Reads questions.build()'s history; makes no API calls of its own. Stdlib only, no JavaScript.
"""
from __future__ import annotations

import datetime as dt
import html
import statistics

# Under 3, a ratio or a median rests on one or two values: one more question or PR moves it
# by half or more, so it says nothing about a trend. 3 is the smallest count with a middle.
MIN_COUNT = 3
WEEK = 7


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def day_text(d: dt.date) -> str:
    return f"{d.day} {d:%b}"


def num(x: float) -> str:
    return f"{x:.1f}"


def days_of(h: dict) -> list[dt.date]:
    first = h["start"].date()
    return [first + dt.timedelta(days=i) for i in range(h["days"])]


def per_day(times, days: list[dt.date]) -> dict[dt.date, int]:
    out = {d: 0 for d in days}
    for t in times:
        d = t.date() if isinstance(t, dt.datetime) else t
        if d in out:
            out[d] += 1
    return out


def weeks(days: list[dt.date]) -> tuple[list[dt.date], list[dt.date] | None]:
    """This week (the last 7 days, today included) and the week before, if the window holds it."""
    return days[-WEEK:], (days[-2 * WEEK:-WEEK] if len(days) >= 2 * WEEK else None)


def direction(now: float, before: float) -> str:
    a, b = num(now), num(before)
    return "the same as" if a == b else ("up from" if now > before else "down from") + f" {b}"


# ---------------------------------------------------------------- the three trends

def questions_per_pr(h: dict) -> dict:
    days = days_of(h)
    asked = per_day([q["created"] for q in h["questions"]], days)
    merged = per_day(h["merged"], days)
    series = [(d, asked[d] / merged[d] if merged[d] else None) for d in days]
    this, before = weeks(days)
    q_now, m_now = sum(asked[d] for d in this), sum(merged[d] for d in this)
    if m_now < MIN_COUNT:
        sentence = (f"Questions per merged PR: too few to tell ({m_now} merged "
                    f"PR{'s' if m_now != 1 else ''} this week).")
        return trend("questions_per_merged_pr", sentence, series, too_few=True)
    r = q_now / m_now
    sentence = f"{num(r)} questions per merged PR this week"
    m_before = sum(merged[d] for d in before) if before else 0
    if before and m_before >= MIN_COUNT:
        d = direction(r, sum(asked[x] for x in before) / m_before)
        sentence += f", {d} the week before."
    else:
        sentence += f" ({q_now} questions, {m_now} PRs); too few the week before to compare."
    return trend("questions_per_merged_pr", sentence, series)


def hours_to_decide(h: dict) -> dict:
    days = days_of(h)
    done = [q for q in h["questions"] if q["hours"] is not None]
    by_day: dict[dt.date, list[float]] = {d: [] for d in days}
    for q in done:
        if q["decided"].date() in by_day:
            by_day[q["decided"].date()].append(q["hours"])
    series = [(d, statistics.median(by_day[d]) if by_day[d] else None) for d in days]
    waiting = len(h["questions"]) - len(done)
    more = f"; {waiting} not decided yet" if waiting else ""
    if len(done) < MIN_COUNT:
        sentence = (f"Hours to decide: too few to tell ({len(done)} "
                    f"question{'s' if len(done) != 1 else ''} decided{more}).")
        return trend("hours_to_decide", sentence, series, too_few=True)
    med = statistics.median(q["hours"] for q in done)
    sentence = f"Median {num(med)} hours to decide ({len(done)} questions{more})."
    return trend("hours_to_decide", sentence, series)


def records_per_day(h: dict) -> dict:
    days = days_of(h)
    counts = per_day(h["records"], days)
    series = [(d, counts[d]) for d in days]
    last, today = h["last_record"], days[-1]
    latest = ("no records yet" if last is None else
              "the latest today" if last >= today else f"none since {day_text(last)}")
    n = len(h["records"])
    if n < MIN_COUNT:
        sentence = (f"Records a day: too few to tell ({n} in {len(days)} days); {latest}.")
        return trend("records_per_day", sentence, series, too_few=True)
    return trend("records_per_day", f"{num(n / len(days))} records a day; {latest}.", series)


LABELS = {"questions_per_merged_pr": "Questions per merged PR",
          "hours_to_decide": "Median hours to decide",
          "records_per_day": "Records"}


def trend(name: str, sentence: str, series: list, too_few: bool = False) -> dict:
    return {"name": name, "sentence": sentence, "too_few": too_few,
            "series": [{"date": d, "value": None if v is None else round(v, 2)} for d, v in series]}


def build(h: dict | None) -> dict | None:
    if h is None:
        return None
    return {"days": h["days"], "first_day": h["start"].date(), "min_count": MIN_COUNT,
            "trends": [questions_per_pr(h), hours_to_decide(h), records_per_day(h)]}


# ---------------------------------------------------------------- rendering

W, H, PAD = 120, 24, 2


def spark(t: dict) -> str:
    """Inline SVG, one point per day, no axes. A day with no value (no PRs merged, nothing
    decided) is a gap. The title and aria-label give every day's value as text."""
    pts = t["series"]
    vals = [p["value"] for p in pts if p["value"] is not None]
    top = max(vals, default=0) or 1
    step = (W - 2 * PAD) / max(len(pts) - 1, 1)

    def xy(i, v):
        return f"{PAD + i * step:.1f},{H - PAD - (v / top) * (H - 2 * PAD):.1f}"

    runs, run = [], []
    for i, p in enumerate(pts):
        if p["value"] is None:
            runs, run = runs + ([run] if run else []), []
        else:
            run.append(xy(i, p["value"]))
    runs += [run] if run else []
    marks = "".join(f'<polyline points="{" ".join(r)}"/>' if len(r) > 1 else
                    f'<circle cx="{r[0].split(",")[0]}" cy="{r[0].split(",")[1]}" r="1.5"/>'
                    for r in runs)
    alt = (f'{LABELS[t["name"]]} by day, {day_text(pts[0]["date"])} to {day_text(pts[-1]["date"])}: '
           + ", ".join("none" if p["value"] is None else f'{p["value"]:g}' for p in pts)) if pts else ""
    return (f'<svg class="spark" role="img" aria-label="{esc(alt)}" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}"><title>{esc(alt)}</title>{marks}</svg>')


def render(tr: dict | None) -> str:
    if tr is None:
        return ""
    items = "".join(f'<li class="{"few" if t["too_few"] else ""}">{spark(t)}'
                    f'<span>{esc(t["sentence"])}</span></li>' for t in tr["trends"])
    note = (f'The last {tr["days"]} days in UTC; "this week" is the last 7. Under '
            f'{tr["min_count"]} merged PRs, decided questions or records a trend says "too few '
            'to tell": one or two values can\'t show a direction. A question is decided when the '
            'owner first adds gov:ruled or ready, or else when it closes.')
    return (f'<h2>What the numbers say</h2><ul class="trends">{items}</ul>'
            f'<p class="muted method">{esc(note)}</p>')
