#!/usr/bin/env python3
"""`swarm classify eval`: score a classifier on a labelled set and write a Markdown report (#1010).

    launcher/swarm classify eval <labelset> [--split dev|test] [--baseline NAME]
                                 [--replay | --live] [--runs N] [--model M]

reads classify/labelsets/<labelset>.yml and classify/data/<labelset>.jsonl, classifies the
split's items with the model classifier (or the named baseline), prints the report and writes
it to classify/reports/<labelset>-<split>-<classifier>.md.

--replay (the default) uses only classify/recordings/ and makes no model calls. --live calls
the model through `claude -p` on the owner's login (GOV-0045), records every reply, and
stops at the label set's max_calls or at swarm.toml's [classify] eval_budget_usd, whichever
comes first. A live run refuses to start unless the label set and labelled set are committed
unchanged, so the bar can't move after a result is known; every report carries both files'
sha256 (GOV-0044). Reports carry no cost figures (evals/README.md, GOV-0033).

The model is --model, else swarm.toml's [classify] model, else claude-haiku-5-5.
Exits 0 when the run passes its pass mark, 1 when it fails it, 2 when it can't run.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import classifier  # noqa: E402
import labelset as lsmod  # noqa: E402
import metrics  # noqa: E402

DEFAULT_MODEL = "claude-haiku-5-5"
MANIFEST = HERE.parent / "swarm.toml"
CONFIG_KEYS = ("model", "eval_budget_usd")


class CantRun(RuntimeError):
    """The eval can't run as asked; the message says why."""


# ---------------------------------------------------------------- config and checks

def config(manifest: Path) -> dict:
    """swarm.toml's [classify] table ({} if the file or table is missing). Raises CantRun if
    the table is bad."""
    try:
        data = tomllib.loads(Path(manifest).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise CantRun(f"can't read {manifest}: {e}") from None
    t = data.get("classify", {})
    if not isinstance(t, dict):
        raise CantRun(f"{manifest}: classify must be a [classify] table")
    bad = [k for k in t if k not in CONFIG_KEYS]
    if bad:
        raise CantRun(f"{manifest}: [classify] has unknown key '{bad[0]}' "
                      f"(allowed: {', '.join(CONFIG_KEYS)})")
    if "model" in t and (not isinstance(t["model"], str) or not t["model"]):
        raise CantRun(f"{manifest}: [classify] model must be a model ID")
    b = t.get("eval_budget_usd")
    if b is not None and (isinstance(b, bool) or not isinstance(b, (int, float)) or b <= 0):
        raise CantRun(f"{manifest}: [classify] eval_budget_usd must be a positive number")
    return t


def uncommitted(paths: list[Path]) -> list[str]:
    """The paths git doesn't have committed exactly as they are on disk."""
    out = []
    for p in paths:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", p.name], cwd=p.parent,
                                 capture_output=True)
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", p.name], cwd=p.parent,
                               capture_output=True)
        if tracked.returncode != 0 or clean.returncode != 0:
            out.append(str(p))
    return out


# ---------------------------------------------------------------- the report

def pct(v: Optional[float]) -> str:
    return "–" if v is None else f"{v * 100:.1f}%"


def pts(pred: Optional[float], gold: Optional[float]) -> str:
    if pred is None or gold is None:
        return "–"
    d = (pred - gold) * 100
    return f"{d:+.1f} pts" if round(d, 1) else "0.0 pts"


def cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render(ls: lsmod.LabelSet, data_sha: str, split: str, who: str, mode: str,
           items: list, preds: dict, m: metrics.Metrics, checks: list) -> str:
    passed = all(c.ok for c in checks)
    out = [f"# Classify eval: {ls.name}, {split} split", "",
           f"- **Classifier:** {who}",
           f"- **Mode:** {mode}",
           f"- **Label set:** `labelsets/{ls.name}.yml` sha256 `{ls.sha}`",
           f"- **Labelled set:** `data/{ls.name}.jsonl` sha256 `{data_sha}`",
           f"- **Items:** {m.n}", "",
           f"**Result: {'PASS' if passed else 'FAIL'}**", "",
           "## Pass mark", "", "| Check | Value | Bar | |", "|---|---|---|---|"]
    out += [f"| {c.what} | {pct(c.value)} | {pct(c.bar)} | {'pass' if c.ok else 'FAIL'} |"
            for c in checks]
    out += ["", "## Overall", "", "| Measure | Value |", "|---|---|",
            f"| Accuracy | {pct(m.accuracy)} ({m.correct} of {m.n}) |",
            f"| Coverage | {pct(m.coverage)} ({m.covered} of {m.n} answered) |",
            f"| Accuracy on covered items | {pct(m.covered_accuracy)} |",
            "", "## Per label", "", "| Label | Gold | Predicted | Correct | Precision | Recall |",
            "|---|---|---|---|---|---|"]
    out += [f"| {lb} | {s.support} | {s.predicted} | {s.correct} | {pct(s.precision)} | "
            f"{pct(s.recall)} |" for lb, s in m.labels.items()]
    cols = ls.label_names + [lsmod.NEEDS_HUMAN]
    out += ["", "## Confusion matrix", "", "Rows are gold labels, columns predicted.", "",
            "| Gold \\ Predicted | " + " | ".join(cols) + " |",
            "|---|" + "---|" * len(cols)]
    out += [f"| {g} | " + " | ".join(str(row[c]) for c in cols) + " |"
            for g, row in m.confusion.items()]
    if m.flags:
        out += ["", "## Flags", "", "On answered items.", "",
                "| Flag | Gold true | Predicted true | Both | Precision | Recall |",
                "|---|---|---|---|---|---|"]
        out += [f"| {f} | {s.support} | {s.predicted} | {s.correct} | {pct(s.precision)} | "
                f"{pct(s.recall)} |" for f, s in m.flags.items()]
    if m.shares:
        out += ["", "## Share error by week", "",
                "Each label's share of the answered items, its share of the gold labels, and "
                "the difference.", "",
                "| Week | " + " | ".join(ls.label_names) + " |",
                "|---|" + "---|" * len(ls.label_names)]
        for week, row in m.shares.items():
            out.append(f"| {week} | " + " | ".join(
                f"{pct(p)} vs {pct(g)} ({pts(p, g)})" for p, g in row.values()) + " |")
    out += ["", "## Items", "", "| Item | Gold | Predicted | Confidence | Evidence |",
            "|---|---|---|---|---|"]
    for it in items:
        p = preds[it.id]
        got = p.label or lsmod.NEEDS_HUMAN
        mark = "" if p.label == it.label else " ✗"
        ev = f"“{cell(p.evidence)}”" if p.evidence else ""
        out.append(f"| {cell(it.id)} | {it.label} | {got}{mark} | {pct(p.confidence)} | {ev} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- the run

def run(name: str, root: Path, split: str = "dev", baseline: Optional[str] = None,
        live: bool = False, runs: Optional[int] = None, model: Optional[str] = None,
        manifest: Path = MANIFEST, out: Optional[Path] = None,
        runner: Callable = classifier.claude_runner,
        uncommitted: Callable = uncommitted, say: Callable = print) -> bool:
    """Score one classifier and write its report. True if it passed. Raises CantRun."""
    if "/" in name or name.startswith("."):
        raise CantRun(f"'{name}' isn't a label set name")
    ls_path, data_path = root / "labelsets" / f"{name}.yml", root / "data" / f"{name}.jsonl"
    try:
        ls = lsmod.load_labelset(ls_path)
        all_items = lsmod.load_items(data_path, ls)
    except lsmod.FormatError as e:
        raise CantRun(str(e)) from None
    items = [it for it in all_items if it.split == split]
    if not items:
        raise CantRun(f"{data_path} has no {split} items")
    dev = [it for it in all_items if it.split == "dev"]

    if baseline is not None:
        if live:
            raise CantRun("--baseline makes no model calls; leave out --live")
        if baseline not in classifier.BASELINES:
            raise CantRun(f"unknown baseline '{baseline}' (known: "
                          f"{', '.join(sorted(classifier.BASELINES))})")
        fn = classifier.BASELINES[baseline]
        classify, who, mode, slug = (lambda it: fn(ls, dev, it)), f"baseline `{baseline}`", \
            "baseline (no model calls)", f"baseline-{baseline}"
    else:
        cfg = config(manifest)
        model = model or cfg.get("model") or DEFAULT_MODEL
        n = ls.runs if runs is None else runs
        if n < 1:
            raise CantRun("--runs must be at least 1")
        cap = None
        if live:
            if cfg.get("eval_budget_usd") is None:
                raise CantRun(f"refused: {manifest} has no [classify] eval_budget_usd, so a live "
                              f"run would have no budget (GOV-0045)")
            loose = uncommitted([ls_path, data_path])
            if loose:
                raise CantRun("refused: commit the pass mark and labelled set before a live run "
                              f"(GOV-0044): {', '.join(loose)} not committed as they are")
            cap = classifier.Cap(ls.max_calls, float(cfg["eval_budget_usd"]))
        rec = classifier.Recordings(root / "recordings", name, model)
        classify = classifier.ModelClassifier(ls, model, rec, n, live, cap, runner)
        who = f"model `{model}`, {n} samples per item, threshold {pct(ls.threshold)}"
        mode, slug = ("live (replies recorded)" if live else "replay (recordings only)"), model

    preds = {}
    try:
        for it in items:
            preds[it.id] = classify(it)
    except classifier.CapReached as e:
        raise CantRun(f"{e}: {len(preds)} of {len(items)} items classified, replies recorded, "
                      f"no report written") from None
    except (classifier.ReplayMissing, classifier.ModelError, ValueError) as e:
        raise CantRun(f"{e}; no report written") from None

    m = metrics.compute(ls, items, preds)
    checks = metrics.check(ls, m)
    report = render(ls, lsmod.sha256(data_path), split, who, mode, items, preds, m, checks)
    out = out or root / "reports" / f"{name}-{split}-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    say(report.rstrip("\n"))
    say(f"\nswarm classify eval: wrote {out}")
    return all(c.ok for c in checks)


def add_eval_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("labelset", help="the label set's name: classify/labelsets/<name>.yml")
    p.add_argument("--split", choices=lsmod.SPLITS, default="dev", help="default: dev")
    p.add_argument("--baseline", metavar="NAME",
                   help=f"score this baseline instead of the model (built in: majority)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--replay", action="store_true",
                      help="use only recorded replies; no model calls (the default)")
    mode.add_argument("--live", action="store_true",
                      help="call the model and record every reply (GOV-0045)")
    p.add_argument("--runs", type=int, help="samples per item (default: the label set's runs, or 3)")
    p.add_argument("--model", help=f"default: swarm.toml [classify] model, or {DEFAULT_MODEL}")
    p.add_argument("--dir", default=str(HERE), help="the classify directory (default: classify/)")
    p.add_argument("--out", help="the report's path (default: <dir>/reports/...)")
    p.add_argument("--manifest", default=str(MANIFEST), help="default: swarm.toml")


def eval_main(args, say: Callable = print, runner: Callable = classifier.claude_runner,
              uncommitted: Callable = uncommitted) -> int:
    try:
        ok = run(args.labelset, Path(args.dir), args.split, args.baseline, args.live, args.runs,
                 args.model, Path(args.manifest), Path(args.out) if args.out else None,
                 runner=runner, uncommitted=uncommitted, say=say)
    except CantRun as e:
        say(f"swarm classify eval: {e}")
        return 2
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="swarm classify")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add_eval_args(sub.add_parser("eval", help="score a classifier on a labelled set"))
    return eval_main(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
