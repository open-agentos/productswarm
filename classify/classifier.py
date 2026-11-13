"""Classifiers: named baselines and the model classifier, with recordings for replay (#1010).

Baselines are plain functions registered by name with @baseline("name"). Each takes the label
set, the dev split's items and one item, and returns a Prediction. `majority` is built in.

ModelClassifier asks a model N times (the label set's `runs`, default 3) for one item and
returns the majority label, confidence = the share of samples that agree with it, and a
quoted evidence line. Below the label set's threshold, or with no single majority, it
answers "needs human" (label None).

Model calls go through a runner: ClaudeRunner runs `claude -p` on the owner's Claude Code
login with no tools and `--max-budget-usd` (GOV-0045). Live runs record every reply in
classify/recordings/<label set>/<model>.jsonl; replay reads only those and calls nothing.
A recording holds the item id, the sample number, a hash of the prompt and the model's
reply: no prompt text, keys or session data (GOV-0044). The hash means a reply recorded
for an older label set or item text isn't replayed for a new one.

Calls stop at the label set's max_calls and at the run's budget (Cap). Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from labelset import Item, LabelSet
from metrics import Prediction

# ---------------------------------------------------------------- baselines

BASELINES: dict[str, Callable] = {}


def baseline(name: str):
    """Register fn(labelset, dev_items, item) -> Prediction as the baseline `name`."""
    def register(fn):
        BASELINES[name] = fn
        return fn
    return register


@baseline("majority")
def majority(labelset: LabelSet, dev: list[Item], item: Item) -> Prediction:
    """The most common gold label in the dev split (ties go to the label listed first)."""
    counts = Counter(it.label for it in dev)
    best = max(labelset.label_names, key=lambda lb: (counts[lb], -labelset.label_names.index(lb)))
    return Prediction(best)


# ---------------------------------------------------------------- prompts and replies

def system_prompt(ls: LabelSet) -> str:
    """The instructions for one label set: every label and flag, and the reply format."""
    out = [f"You classify one piece of text against the label set '{ls.name}'."]
    if ls.description.strip():
        out.append(ls.description.strip())
    out += ["", "Labels:"]
    for lb in ls.labels:
        out.append(f"- {lb.name}: {lb.definition}")
        out += [f"  - Boundary: {b}" for b in lb.boundary]
        out += [f"  - Example: {e}" for e in lb.examples]
    if ls.flags:
        out += ["", "Flags (answer true or false for each):"]
        out += [f"- {f.name}: {f.definition}" for f in ls.flags]
    flags = ", ".join(f'"{f.name}": true or false' for f in ls.flags)
    out += ["", "Reply with only one JSON object and nothing else:",
            '{"label": "<one label name>", "flags": {' + flags + '}, '
            '"evidence": "<one line quoted exactly from the text that decided the label>"}']
    return "\n".join(out)


def user_prompt(item: Item) -> str:
    return "Text to classify:\n<<<\n" + item.text + "\n>>>"


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\0" + user).encode()).hexdigest()[:16]


def parse_reply(ls: LabelSet, reply: str) -> Optional[dict]:
    """{"label", "flags", "evidence"} from a reply, or None if it names no known label."""
    m = re.search(r"\{.*\}", reply or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or d.get("label") not in ls.label_names:
        return None
    flags = d.get("flags") if isinstance(d.get("flags"), dict) else {}
    ev = d.get("evidence") if isinstance(d.get("evidence"), str) else ""
    return {"label": d["label"], "evidence": " ".join(ev.split()),
            "flags": {f: flags.get(f) is True for f in ls.flag_names}}


def vote(ls: LabelSet, replies: list[str]) -> Prediction:
    """The majority of the samples' replies; "needs human" below the threshold or on a tie.
    A reply naming no known label is a sample with no vote."""
    parsed = [parse_reply(ls, r) for r in replies]
    counts = Counter(p["label"] for p in parsed if p)
    if not counts:
        return Prediction(None, 0.0)
    ranked = counts.most_common()
    top, n = ranked[0]
    confidence = round(n / len(replies), 4)
    if (len(ranked) > 1 and ranked[1][1] == n) or confidence < ls.threshold:
        return Prediction(None, confidence)
    agree = [p for p in parsed if p and p["label"] == top]
    flags = {f: sum(p["flags"][f] for p in agree) * 2 > len(agree) for f in ls.flag_names}
    return Prediction(top, confidence, agree[0]["evidence"], flags)


# ---------------------------------------------------------------- recordings

class ReplayMissing(LookupError):
    """--replay needs a reply that was never recorded."""


class Recordings:
    """classify/recordings/<label set>/<model>.jsonl: one JSON object per recorded reply."""

    def __init__(self, root: Path, labelset: str, model: str):
        self.path = Path(root) / labelset / f"{model}.jsonl"
        self._by_key = None

    def _load(self) -> dict:
        if self._by_key is None:
            self._by_key = {}
            if self.path.exists():
                for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                        self._by_key[(d["item"], d["prompt"], d["sample"])] = d["reply"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        raise ValueError(f"{self.path}: line {n} isn't a recording") from None
        return self._by_key

    def get(self, item: str, prompt: str, sample: int) -> Optional[str]:
        return self._load().get((item, prompt, sample))

    def add(self, item: str, prompt: str, sample: int, reply: str) -> None:
        self._load()[(item, prompt, sample)] = reply
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"item": item, "sample": sample, "prompt": prompt, "reply": reply},
                               ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- model calls

class CapReached(RuntimeError):
    """A live run reached its call cap or its budget; no more calls are made."""


class ModelError(RuntimeError):
    """The model call failed."""


class Cap:
    """A live run's limits: the label set's max_calls, and the run's budget in USD
    (GOV-0045). Each call is passed what is left of the budget as --max-budget-usd."""

    def __init__(self, max_calls: int, budget_usd: float):
        self.max_calls, self.budget = max_calls, budget_usd
        self.calls, self.spent = 0, 0.0

    def take(self) -> float:
        """Count one call and return its budget, or raise CapReached."""
        if self.calls >= self.max_calls:
            raise CapReached(f"stopped at the label set's max_calls ({self.max_calls}) after "
                             f"{self.calls} model calls")
        left = round(self.budget - self.spent, 4)
        if left <= 0:
            raise CapReached(f"stopped at the run's budget (swarm.toml [classify] "
                             f"eval_budget_usd) after {self.calls} model calls")
        self.calls += 1
        return left


def claude_command(model: str, system: str, budget: float) -> list[str]:
    """`claude -p` on the owner's login, with no tools, no MCP servers, no saved session."""
    return ["claude", "-p", "--model", model, "--output-format", "json", "--tools", "",
            "--strict-mcp-config", "--no-session-persistence", "--system-prompt", system,
            "--max-budget-usd", f"{budget:.4f}"]


def claude_runner(model: str, system: str, user: str, budget: float) -> tuple[str, float]:
    """(the reply, its cost in USD) from one `claude -p` call, user prompt on stdin. It runs in
    an empty temporary directory, so no project CLAUDE.md is read into the prompt."""
    with tempfile.TemporaryDirectory(prefix="classify-") as cwd:
        try:
            r = subprocess.run(claude_command(model, system, budget), input=user, cwd=cwd,
                               capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ModelError(f"claude -p didn't run: {e}") from None
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise ModelError(f"claude -p exited {r.returncode} without a JSON result: "
                         f"{(r.stderr or r.stdout).strip()[:200]}") from None
    if not isinstance(out, dict):
        raise ModelError("claude -p's result isn't a JSON object")
    cost = float(out.get("total_cost_usd") or 0)
    if out.get("is_error") or out.get("subtype") != "success":
        raise ModelError(f"claude -p ended with {out.get('subtype') or 'an error'}")
    return str(out.get("result", "")), cost


class ModelClassifier:
    """The model classifier: `runs` samples per item, by live calls or from recordings."""

    def __init__(self, ls: LabelSet, model: str, recordings: Recordings, runs: int,
                 live: bool = False, cap: Optional[Cap] = None,
                 runner: Callable = claude_runner):
        if live and cap is None:
            raise ValueError("a live run needs a Cap")
        self.ls, self.model, self.rec, self.runs = ls, model, recordings, runs
        self.live, self.cap, self.runner = live, cap, runner
        self.system = system_prompt(ls)

    def __call__(self, item: Item) -> Prediction:
        user = user_prompt(item)
        key = prompt_hash(self.system, user)
        replies = []
        for k in range(self.runs):
            if self.live:
                budget = self.cap.take()
                reply, cost = self.runner(self.model, self.system, user, budget)
                self.cap.spent += cost
                self.rec.add(item.id, key, k, reply)
            else:
                reply = self.rec.get(item.id, key, k)
                if reply is None:
                    raise ReplayMissing(f"no recording of sample {k + 1} for item '{item.id}' "
                                        f"with this label set and text in {self.rec.path}; "
                                        f"a --live run records it")
            replies.append(reply)
        return vote(self.ls, replies)
