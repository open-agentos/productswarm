# Phase 0 runbook

Phase 0 runs the governance convention **by hand** to learn what agents actually ask before anything is automated. Expect two to three weeks of normal agent work.

## What we're testing

| # | Hypothesis | How we'll know |
|---|---|---|
| H1 | Agents can tell when a decision isn't theirs | Few silent oversteps found in review; questions are raised at sensible moments |
| H2 | Agents classify decisions well enough to route them | `gov:misclassified` rate under ~25%, and no one-way door rated two-way |
| H3 | The default-action field keeps the fleet moving | Most questions are non-blocking; defaults that stood were acceptable |
| H4 | A small set of shapes covers almost everything | Few questions that fit no row in §3 |
| H5 | Precedent gets reused | Later questions cite earlier rulings; repeats of the same question fall over time |

## Setup (once)

1. Copy into the repo root:
   - `GOVERNANCE.md`
   - `governance/`
   - `.github/ISSUE_TEMPLATE/gov-question.yml`
2. Replace the owner handle and the bot names in `governance/jurisdictions.yml`, then adjust the domains to suit the repo.
3. Append `.github/CODEOWNERS.governance` (portable snippet with `@OWNER` placeholders) to `.github/CODEOWNERS`. Turn on branch protection with "Require review from Code Owners".
4. Run `./governance/setup-labels.sh owner/repo`.
5. Paste `AGENTS-snippet.md` into `CLAUDE.md`/`AGENTS.md` and every agent role prompt.
6. **If this runs on an AgentOS repo, keep intake off `gov:` issues.** Agent Intake fires on issue and comment events. Add an exclusion for issues labelled `gov:question` (or run Phase 0 on a repo without intake), and make sure the bot identities are in `INTAKE_EXCLUDE_ACTORS`. Otherwise a deliberation thread will spawn stubs, as the stacked-PR loop did.

## The manual loop (human)

Do this once a day, in a single time-boxed sitting:

1. **Triage new `gov:question` issues.**
   - Check the asker's classification and shape.
   - If either is wrong, add `gov:misclassified` with a one-line reason, and set the correct `gov:shape/*` label.
2. **Route by shape.**
   - *Authoritative / advice where you are the owner:* rule, or ask for the advice round first.
   - *Empirical:* confirm the success criterion is written down and tell the agent to run the experiment.
   - *Consent:* label `gov:deliberating` and note the deadline in a comment.
   - *Committee:* post a convening comment that names the members and their roles. Include a challenger, and use at least two different models or evidence bases.
   - *Vote:* post the eligible list and the deadline.
3. **Close finished ones.** Write the decision record from the template, add a row to `INDEX.md`, open the PR with `Closes #N`, and merge it. Then comment the one-line ruling on the issue and label it `gov:ruled`.
4. **Sweep for lapses.** Anything past its TTL becomes `gov:lapsed`.

To run a committee by hand, start each member as a separate session with the issue URL, its role, and the turn format from GOVERNANCE.md §7. Use different models via OpenRouter where you can.

## Observation log

**Started 2026-11-01 (productswarm).** Setup notes:

- The fleet is manually started Claude Code sessions (see `roles/`), not AgentOS. There is no intake, so setup step 6 doesn't apply.
- ~~All sessions act through the owner's GitHub account.~~ Fixed 2026-11-01: each role is a GitHub App (`productswarm-<role>[bot]`), and sessions are launched with `ops/swarm-session`. Votes (§7.5) can now be tallied by verified identity. No App has `workflows` or `administration` permission.
- Merge-as-ratification needs a ruleset on `main` requiring code-owner review. The private repo on the free plan can't have one yet, so until then it rests on sessions being told never to merge. Watch for any App that merges or approves.
- Workload: the swarm dashboard and session heartbeat in `PRODUCT.md`.

Add a row for every question. This file is the Phase 0 deliverable.

| Issue | Domain | Asker's shape | Correct shape | Blocking? | Default stood? | Hours to ruling | Rounds | Notes (what the agent got wrong or right; did it fit any shape?) |
|---|---|---|---|---|---|---|---|---|
| #14 | architecture | authoritative | authoritative | no | no: owner chose option 4 (issue comments) over the recommended option 3 (local spool + sync) | 13.3 | 0 | Raised by builder unprompted, but the planner had already flagged it on #2. Strong options: noticed option 2 would widen App permissions (a security question in itself). Ruled by owner comment; converted to GOV-0003 by hand. |
| #15 | security | authoritative | authoritative | yes (`gov:blocking`) | n/a (blocking) | 13.2 | 0 | Recommended minimal fields; owner widened to prompt text, tool names, token counts. "Tool requests" was ambiguous, and safeguards for prompt text were unstated, so clarifying questions were needed before writing a one-way ruling. Ruled by owner comment; converted to GOV-0002 by hand. |

**Other observations (2026-11-02)**

- **Planner deferred asking.** The planner spotted both #14 and #15 on #2 but left raising them "when a builder picks it up". Unclear whether a planner should ask itself; candidate for a rule or a role-prompt change.
- **Owners rule in comments.** Both rulings arrived as issue comments, not records. Converting them took a drafting step plus clarifying questions. Evidence for Phase 1 `gov rule`: turn an owner comment into a record PR, and ask back when the comment is ambiguous for a one-way decision.
- **Ruling PRs show the owner as author** because they were drafted through the owner's `gh` login. Fine while merge is the ratifying act, but a drafting App identity would keep authorship honest.
- **Model signatures disagree.** Planner signed `claude-opus-4-8[1m]`, builder `claude-opus-5-5`. Self-reported; the launcher should record the actual model before the committee diversity rule relies on it.
- **H5 test pending.** The builder's schema PR #16 was written on the defaults. Watch whether it finds GOV-0002/0003 by checking precedent, unprompted.

Also note anything that **should** have been a question and wasn't (oversteps found in PR review). Those are the misses that a classifier can't learn from the issue list alone.

## Exit criteria (move to Phase 1 when all are true)

- At least 20 real questions logged across at least 4 domains.
- You can name the 3 shapes that cover most questions. Phase 1 automates those first.
- You've seen at least one committee and one lapse play out end to end.
- You've drafted a revised GOVERNANCE.md §2–§3 from what the log shows. Expect it to change, because the first taxonomy is a guess.

## What Phase 0 deliberately leaves out

There is no classifier, no automatic index regeneration, no Slack gateway, no agent notification on ruling, and no enforcement beyond CODEOWNERS. If you find yourself wanting one of these during Phase 0, note it in the log; that is evidence for the Phase 1 build order.
