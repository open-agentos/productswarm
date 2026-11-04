"""Committee Discussions and their gov:questions, for the dashboard (#353).

Reads every Discussion in the "Committees" category, the gov:question each one serves, and
the decision record for that question, and derives where the committee stands: status,
§7.2 diversity, the next seat to post, rounds used (§7.4) and posts per member per day (§8).

The format is #314's body (members table, six rules, `## Round N: <seat>` posts), plus the
question marker and `###` headings of the Discussion form (#352, option 3; #371). Anything
else is "unparsed": no convention is invented beyond those.

What it keeps is deliberately thin, because the page is public (#348, GOV-0014): from each
round post only its round, seat, author, time, link, signature model and the first bold
phrase of its Recommendation; from the owner's comments on the question only which of the
convening, summary and ruling comments exist, when, and their links. No other text, so a
cost line in a convener's summary can never reach the page.

fetch() never raises and build() never fails on bad data: problems become short notes and
the rest of the page builds.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "governance" / "decisions"
JURISDICTIONS = ROOT / "governance" / "jurisdictions.yml"

CATEGORY = "committees"   # the Discussion category's slug
MAX_ROUNDS = 3            # GOVERNANCE.md §7.4
DAILY_POSTS = 6           # GOVERNANCE.md §8: at most 6 comments per question per day
PHRASE_LEN = 80
NO_ACCESS = "can't read Discussions: the token needs `discussions: read`"

# The owner's comments on the question, by how they start. Only these prefixes are kept.
OWNER_HEADS = {"convening": "**Convening a committee**",
               "summary": "**Convener's summary**",
               "ruling": "**Ruling:"}

MARKER_RE = re.compile(r"<!--\s*productswarm-committee\s+question=(\S+?)\s*-->")
TITLE_RE = re.compile(r"^\s*Committee for #(\d+)\s*:")
HEADING_RE = re.compile(r"^#{1,3}\s", re.M)
APP_RE = re.compile(r"productswarm-([a-z0-9]+(?:-[a-z0-9]+)*)")
ORDER_RE = re.compile(r"in order:\s*([^.\n]+)", re.I)
ROUND_RE = re.compile(r"\A\s*#{1,3}\s*Round\s+(\d+)\s*:\s*([^\n(]+?)\s*(?:\([^\n]*\))?\s*$", re.M)
RECO_RE = re.compile(r"^#{2,4}\s*Recommendation\b[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)", re.M | re.S)
BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
SIGN_RE = re.compile(r"^--\s*([\w-]+)\s*\(([^)\n]+)\)\s*$", re.M)

CATEGORY_Q = """query($owner: String!, $name: String!, $slug: String!) {
  repository(owner: $owner, name: $name) { discussionCategory(slug: $slug) { id } } }"""

COMMENT_FIELDS = "pageInfo { hasNextPage endCursor } nodes { author { login } createdAt url body }"

DISCUSSIONS_Q = """query($owner: String!, $name: String!, $cat: ID!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussions(categoryId: $cat, first: 25, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { id number title body url createdAt author { login }
              comments(first: 100) { %s } } } } }""" % COMMENT_FIELDS

COMMENTS_Q = """query($id: ID!, $after: String) {
  node(id: $id) { ... on Discussion { comments(first: 100, after: $after) { %s } } } }""" % COMMENT_FIELDS


# ---------------------------------------------------------------- reading GitHub

def _graphql(gh_json, query: str, **variables) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        if v is not None:
            args += ["-f", f"{k}={v}"]
    out = gh_json(*args)
    if not isinstance(out, dict) or not isinstance(out.get("data"), dict):
        raise RuntimeError("no data from gh api graphql")
    return out["data"]


def _access_note(err: Exception) -> str:
    text = str(err)
    if re.search(r"not accessible|forbidden|insufficient|scope|permission", text, re.I):
        return NO_ACCESS
    return "can't read Discussions"


def fetch(repo: str, gh_items, gh_json) -> dict:
    """The committee Discussions (with all their top-level comments) and, for each, its
    linked question and that question's comments, as plain API data. Never raises: a token
    without Discussions access gives a note and no Discussions."""
    out = {"discussions": [], "questions": {}, "notes": []}
    owner, _, name = repo.partition("/")
    try:
        cat = _graphql(gh_json, CATEGORY_Q, owner=owner, name=name, slug=CATEGORY)
        cat = ((cat.get("repository") or {}).get("discussionCategory") or {}).get("id")
        if not cat:
            out["notes"].append("no Committees Discussion category")
            return out
        after = None
        while True:
            page = _graphql(gh_json, DISCUSSIONS_Q, owner=owner, name=name, cat=cat, after=after)
            conn = page["repository"]["discussions"]
            for d in conn["nodes"]:
                comments = d.pop("comments")
                nodes, info = list(comments["nodes"]), comments["pageInfo"]
                while info.get("hasNextPage"):
                    more = _graphql(gh_json, COMMENTS_Q, id=d["id"], after=info["endCursor"])
                    more = more["node"]["comments"]
                    nodes += more["nodes"]
                    info = more["pageInfo"]
                d["comments"] = nodes
                out["discussions"].append(d)
            if not conn["pageInfo"].get("hasNextPage"):
                break
            after = conn["pageInfo"]["endCursor"]
    except Exception as e:   # degrade, don't fail: the rest of the page still builds
        out["discussions"] = []
        out["notes"].append(_access_note(e))
        return out

    for d in out["discussions"]:
        n, _ = question_number(d)
        if n is None or n in out["questions"]:
            continue
        try:
            out["questions"][n] = {
                "issue": gh_json("api", f"repos/{repo}/issues/{n}"),
                "comments": gh_items(f"repos/{repo}/issues/{n}/comments?per_page=100")}
        except Exception:
            out["notes"].append(f"#{d['number']}: can't read question #{n}")
    return out


# ---------------------------------------------------------------- parsing one Discussion

def question_number(d: dict) -> tuple[int | None, str | None]:
    """The linked question: the marker if it holds a number, else the title. A note when
    the two disagree (the marker wins)."""
    m = MARKER_RE.search(d.get("body") or "")
    marker = int(m.group(1)) if m and m.group(1).isdigit() else None
    t = TITLE_RE.match(d.get("title") or "")
    title = int(t.group(1)) if t else None
    if marker is not None and title is not None and marker != title:
        return marker, f"#{d.get('number')}: marker says #{marker}, title says #{title}; using #{marker}"
    return (marker if marker is not None else title), None


def section(body: str, name: str) -> str | None:
    """The text under a `## name` or `### name` heading, up to the next heading."""
    m = re.search(rf"^#{{2,3}}\s*{name}\b[^\n]*\n", body, re.M | re.I)
    if not m:
        return None
    rest = body[m.end():]
    nxt = HEADING_RE.search(rest)
    return rest[:nxt.start()] if nxt else rest


def app_login(login: str | None) -> str:
    """REST shows an App as productswarm-<role>[bot], GraphQL as productswarm-<role>."""
    login = login or ""
    if login.startswith("productswarm-") and not login.endswith("[bot]"):
        return login + "[bot]"
    return login


def members(text: str) -> list[dict] | None:
    """Rows of the members table: | Role | Member | Model | Main evidence |. None if any
    row lacks an App or a model (an unfilled form, say)."""
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set("".join(cells)) <= set("-: ") or cells[0].lower() == "role":
            continue
        seat = re.sub(r"[*_`]", "", cells[0]).strip().lower()
        app = APP_RE.search(cells[1])
        model = re.search(r"`([^`]+)`", cells[2]) or re.match(r"\s*(\S+)", cells[2])
        if not seat or not app or not model:
            return None
        rows.append({"seat": seat, "role": app.group(1), "app": f"productswarm-{app.group(1)}[bot]",
                     "model": model.group(1), "evidence": re.sub(r"\s+", " ", cells[3])})
    return rows or None


def post_order(rules: str, seats: list[str]) -> list[str] | None:
    """Rule 1's post order, e.g. "members post in order: proposer, challenger, domain reviewer"."""
    m = ORDER_RE.search(rules)
    if not m:
        return None
    order = [s.strip().lower() for s in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1)) if s.strip()]
    return order if order and all(s in seats for s in order) and len(set(order)) == len(order) else None


def phrase(body: str) -> str | None:
    """The first bold phrase of the Recommendation section, cut to about PHRASE_LEN."""
    m = RECO_RE.search(body)
    b = BOLD_RE.search(m.group(1)) if m else None
    if not b:
        return None
    text = re.sub(r"\s+", " ", b.group(1)).strip().rstrip(".:;,").strip()
    return text if len(text) <= PHRASE_LEN else text[:PHRASE_LEN - 1].rstrip() + "…"


def parse_ts(s: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def records(path: Path = DECISIONS) -> dict[int, dict]:
    """Decision records by the question they answer, from each file's front matter."""
    out = {}
    for f in sorted(path.glob("GOV-*.md")) if path.is_dir() else []:
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = re.match(r"\A---\n(.*?)\n---", text, re.S)
        if not fm:
            continue
        q = re.search(r'^question:\s*["\']?#(\d+)["\']?\s*$', fm.group(1), re.M)
        rid = re.search(r"^id:\s*(\S+)", fm.group(1), re.M)
        status = re.search(r"^status:\s*(\S+)", fm.group(1), re.M)
        if q and rid:
            out[int(q.group(1))] = {"id": rid.group(1), "status": status.group(1) if status else None}
    return out


def owner_login(path: Path = JURISDICTIONS) -> str | None:
    """humans.owner from governance/jurisdictions.yml, without the @."""
    try:
        m = re.search(r'^\s+owner:\s*["\']?@([A-Za-z0-9-]+)', path.read_text(), re.M)
    except OSError:
        return None
    return m.group(1) if m else None


def same(phrases: list[str | None]) -> bool:
    norm = {re.sub(r"\s+", " ", p).strip().lower() for p in phrases if p}
    return len(norm) == 1 and None not in phrases


def committee(d: dict, question: dict | None, recs: dict[int, dict], owner: str | None) -> dict:
    """One Discussion's committee, or {"status": "unparsed"} if it doesn't match #314's layout."""
    base = {"discussion": d.get("number"), "title": d.get("title"), "url": d.get("url"), "notes": []}
    body = d.get("body") or ""
    n, note = question_number(d)
    if note:
        base["notes"].append(note)
    table = section(body, "Members")
    rules = section(body, "Rules")
    seats = members(table) if table else None
    order = post_order(rules, [s["seat"] for s in seats]) if rules and seats else None
    if n is None or not order:
        return {**base, "status": "unparsed", "notes": base["notes"] + [f"#{d.get('number')}: unparsed"]}
    by_seat = {s["seat"]: s for s in seats}

    # Round posts: top-level, headed `Round N: <seat>`, by that seat's App.
    posts, seen = [], set()
    for c in sorted(d.get("comments") or [], key=lambda c: c.get("createdAt") or ""):
        m = ROUND_RE.match(c.get("body") or "")
        if not m:
            continue
        rnd, seat = int(m.group(1)), m.group(2).strip().lower()
        member = by_seat.get(seat)
        if not member or app_login((c.get("author") or {}).get("login")) != member["app"]:
            continue
        if not 1 <= rnd <= MAX_ROUNDS or (rnd, seat) in seen:
            continue
        seen.add((rnd, seat))
        sig = SIGN_RE.findall(c.get("body") or "")
        model = sig[-1][1].strip() if sig else None
        posts.append({"round": rnd, "seat": seat, "author": member["app"], "ts": parse_ts(c.get("createdAt")),
                      "url": c.get("url"), "recommendation": phrase(c.get("body") or ""),
                      "model": model, "model_differs": model is not None and model != member["model"]})

    # The owner's comments on the question: which exist, when, and their links. No text.
    q_issue = (question or {}).get("issue") or {}
    q_comments = (question or {}).get("comments") or []
    heads = {k: None for k in OWNER_HEADS}
    for c in q_comments:
        if not owner or (c.get("user") or {}).get("login") != owner:
            continue
        text = (c.get("body") or "").lstrip()
        for k, prefix in OWNER_HEADS.items():
            if heads[k] is None and text.startswith(prefix):
                heads[k] = {"ts": parse_ts(c.get("created_at")), "url": c.get("html_url")}
    labels = [lb.get("name") for lb in q_issue.get("labels") or []]
    record = recs.get(n)

    # Where the rounds stand.
    rounds_used = max((p["round"] for p in posts), default=0)
    done = {(p["round"], p["seat"]) for p in posts}
    last = max((order.index(p["seat"]) for p in posts if p["round"] == rounds_used), default=-1)
    missed = [{"round": r, "seat": s} for r in range(1, rounds_used + 1) for i, s in enumerate(order)
              if (r, s) not in done and (r < rounds_used or i < last)]
    agree = rounds_used > 0 and all((rounds_used, s) in done for s in order) and \
        same([p["recommendation"] for p in posts if p["round"] == rounds_used])
    stopped_early = bool(agree and rounds_used < MAX_ROUNDS and re.search(r"stop early", rules, re.I))
    if heads["summary"] or heads["ruling"] or record:
        next_seat = None
    elif not posts:
        next_seat = order[0]
    elif last + 1 < len(order):
        next_seat = order[last + 1]
    elif stopped_early or rounds_used >= MAX_ROUNDS:
        next_seat = None
    else:
        next_seat = order[0]

    if record:
        status = f"record {record['id']}"
    elif heads["ruling"]:
        status = "ratified"
    elif heads["summary"]:
        status = "summary"
    elif posts:
        status = f"round {rounds_used}"
    else:
        status = "convened"

    # §8: posts per member per UTC day, across the Discussion and its question.
    apps = {s["app"] for s in seats}
    counts: dict[tuple[str, dt.date], int] = {}
    stamps = [(app_login((c.get("author") or {}).get("login")), c.get("createdAt")) for c in d.get("comments") or []]
    stamps += [(app_login((c.get("user") or {}).get("login")), c.get("created_at")) for c in q_comments]
    for app, ts in stamps:
        t = parse_ts(ts)
        if app in apps and t:
            counts[(app, t.date())] = counts.get((app, t.date()), 0) + 1
    over = [{"app": a, "day": day, "count": k} for (a, day), k in sorted(counts.items()) if k > DAILY_POSTS]

    models = {s["model"] for s in seats}
    evidence = {s["evidence"].lower() for s in seats}
    return {**base, "status": status, "question": n,
            "question_url": q_issue.get("html_url"), "question_state": q_issue.get("state"),
            "ruled": "gov:ruled" in labels, "owner_comments": heads, "record": record,
            "members": seats, "order": order,
            "diversity": {"models": len(models), "evidence": len(evidence),
                          "met": len(models) >= 2 or len(evidence) >= 2},
            "posts": posts, "rounds_used": rounds_used, "max_rounds": MAX_ROUNDS, "missed": missed,
            "next_seat": next_seat, "stopped_early": stopped_early, "over_limit": over}


def build(raw: dict | None, decisions: Path = DECISIONS, owner: str | None = None) -> dict:
    """Every committee, newest Discussion first, and the notes to show beside them."""
    if not raw:
        return {"committees": [], "notes": []}
    recs = records(decisions)
    owner = owner or owner_login()
    out, notes = [], list(raw.get("notes") or [])
    questions = raw.get("questions") or {}
    for d in sorted(raw.get("discussions") or [], key=lambda d: -(d.get("number") or 0)):
        try:
            n, _ = question_number(d)
            c = committee(d, questions.get(n) or questions.get(str(n)), recs, owner)
        except Exception:   # degrade, don't fail
            c = {"discussion": d.get("number"), "title": d.get("title"), "url": d.get("url"),
                 "status": "unparsed", "notes": [f"#{d.get('number')}: unparsed"]}
        notes += c["notes"]
        out.append(c)
    return {"committees": out, "notes": notes}
