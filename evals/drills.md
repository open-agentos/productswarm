# Drills

Scripted drills that show a Goal's capability on the scratch repo (`open-agentos/productswarm-scratch`), per GOV-0040. Each drill records its steps, links and the output it produced.

## The merger refuses an unreviewed revert (M2 criterion 4, #890)

**Result: refused.** The merger didn't merge the PR. Its reason was `productswarm-reviewer[bot] hasn't approved at head b8ef203`.

**The PR.** [productswarm-scratch#4](https://github.com/open-agentos/productswarm-scratch/pull/4), `Revert "first commit" (drill: unreviewed revert)`, opened by `productswarm-builder[bot]` and closing [productswarm-scratch#2](https://github.com/open-agentos/productswarm-scratch/issues/2):

- It reverts `374023b` (the scratch repo's first commit, which added `README.md`), so it deletes `README.md`. That is the only merged change outside `.github/`. Reverting the merged #1 would touch a workflow, and the merger refuses workflow PRs for that reason alone, so it couldn't show the missing review.
- Head `b8ef2035b19a4066c51315d3a61787a6754b312a`. No reviews of any kind. The `tests` check passed.
- productswarm-scratch#2 is a sub-issue of #890, which sits under M2 (#684). That makes it go under GOV-0031, so the merger gets past `not go` and reaches the review check.

**Steps.**

1. The builder opened productswarm-scratch#2, the drill issue, and the owner linked it under #890 (the builder App gets 403 adding sub-issues).
2. Branched `builder/2-revert-first-commit` from scratch's `main`, ran `git revert 374023b`, pushed it, and opened #4. Nobody asked for a review.
3. On 2026-11-12 at 13:57 UTC, from productswarm's `main` (`69be1ac`), ran the merger by hand against that PR, once for each command below. Neither command merges or comments: `plan` writes nothing, and `run --dry-run` only prints.

**Output.**

```
$ python3 launcher/merger.py plan --repo open-agentos/productswarm-scratch --pr 4
#4 b8ef2035b19a4066c51315d3a61787a6754b312a miss: productswarm-reviewer[bot] hasn't approved at head b8ef203
merger: mode live: 0 PR(s) would merge (--pr 4)

$ python3 launcher/merger.py run --dry-run --repo open-agentos/productswarm-scratch --pr 4
#4 b8ef2035b19a4066c51315d3a61787a6754b312a miss: productswarm-reviewer[bot] hasn't approved at head b8ef203
merger: live acts as shadow: the shadow bar isn't met (0 of 10 PRs with a "would merge" comment; or a day since the first)
merger: mode live (dry run): 0 PR(s) would merge
```

The merger also reads the scratch repo on its own now: `swarm.toml` lists it under `[org]`. Its default multi-repo `plan` (no `--repo`) printed the same miss in a `merger: repo open-agentos/productswarm-scratch` block:

```
merger: repo open-agentos/productswarm-scratch
#4 b8ef2035b19a4066c51315d3a61787a6754b312a miss: productswarm-reviewer[bot] hasn't approved at head b8ef203
merger: mode live: 0 PR(s) would merge
```

`--repo` alone counts only that repo's shadow comments, so the dry run says live acts as shadow there. The PR is a miss before that matters: shadow or live, the missing approval stops the merge.

**Leave scratch#4 open and unreviewed.** It stays as the drill's evidence. Don't approve or merge it.
