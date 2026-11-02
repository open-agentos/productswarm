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
3. **Close finished ones.** Answer on the issue and label it `gov:ruled` (and `ready` when the next stage may start, per GOV-0006). If it needs a record, the docs role writes it from the template, adds a row to `INDEX.md` and opens the PR with `Closes #N` (GOV-0007). Check the PR against your answer, merge it, then comment the one-line ruling on the issue.
4. **Sweep for lapses.** Anything past its TTL becomes `gov:lapsed`.

To run a committee by hand, start each member as a separate session with the issue URL, its role, and the turn format from GOVERNANCE.md §7. Use different models via OpenRouter where you can.

## Observation log

**Started 2026-11-01 (productswarm).** Setup notes:

- The fleet is manually started Claude Code sessions (see `roles/`), not AgentOS. There is no intake, so setup step 6 doesn't apply.
- ~~All sessions act through the owner's GitHub account.~~ Fixed 2026-11-01: each role is a GitHub App (`productswarm-<role>[bot]`), and sessions are launched with `ops/swarm-session`. Votes (§7.5) can now be tallied by verified identity. No App has `workflows` or `administration` permission.
- Merge-as-ratification needs a ruleset on `main` requiring code-owner review. The private repo on the free plan can't have one yet, so until then it rests on sessions being told never to merge. Watch for any App that merges or approves.
- 2026-11-02: the repo is now public, so rulesets are available. Ruleset "main: owner ratifies" (code-owner review, no force-push or deletion, admin bypass for the owner's own ruling PRs) was created disabled for the owner to enable.
- Workload: the swarm dashboard and session heartbeat in `PRODUCT.md`.

Add a row for every question. This file is the Phase 0 deliverable.

| Issue | Domain | Asker's shape | Correct shape | Blocking? | Default stood? | Hours to ruling | Rounds | Notes (what the agent got wrong or right; did it fit any shape?) |
|---|---|---|---|---|---|---|---|---|
| #14 | architecture | authoritative | authoritative | no | no: owner chose option 4 (issue comments) over the recommended option 3 (local spool + sync) | 13.3 | 0 | Raised by builder unprompted, but the planner had already flagged it on #2. Strong options: noticed option 2 would widen App permissions (a security question in itself). Ruled by owner comment; converted to GOV-0003 by hand. |
| #15 | security | authoritative | authoritative | yes (`gov:blocking`) | n/a (blocking) | 13.2 | 0 | Recommended minimal fields; owner widened to prompt text, tool names, token counts. "Tool requests" was ambiguous, and safeguards for prompt text were unstated, so clarifying questions were needed before writing a one-way ruling. Ruled by owner comment; converted to GOV-0002 by hand. |
| #26 | architecture | authoritative | authoritative | no | yes | 0.15 | 0 | How to build the page. Owner agreed with the recommendation by comment and said a record wasn't needed ("temporary decision on a very specific detail"). No record. |
| #28 | spend | authoritative | authoritative | no | partly: owner added "record plan type if possible" | 0.5 | 1 | Cost method. Owner's comment added a requirement; the builder checked feasibility (not derivable from the transcript) and raised #31 for the part that touched GOV-0002. No record. |
| #31 | security | authoritative | authoritative | yes | n/a (blocking) | 0.06 | 0 | Spun off #28. Good precedent check: cited GOV-0002 and noted an owner comment is direction, not a ruling. Owner: do nothing for now. No record; correctly closed as "not now" rather than a ruling. |
| #32 | ci-and-workflows | authoritative | authoritative | yes | n/a (blocking) | 0.1 | 0 | Workflow trigger and token. Owner chose option 1 by comment and wrote the workflow file himself in the web UI (Apps lack `workflows`, as designed). No record. |
| #33 | external | authoritative | authoritative | yes | n/a (blocking) | 0.1 | 0 | Dashboard visibility: one-way, external blast radius. Owner chose public Pages with noindex by comment. No record, though this is the kind of decision §5 says must have one. |
| #36 | security | authoritative | | no | | | | Raised by the owner's coordinating session (not a role) after the repo went public: do GOV-0002/0003 still hold? |

**Other observations (2026-11-02)**

- **Planner deferred asking.** The planner spotted both #14 and #15 on #2 but left raising them "when a builder picks it up". Unclear whether a planner should ask itself; candidate for a rule or a role-prompt change.
- **Owners rule in comments.** Both rulings arrived as issue comments, not records. Converting them took a drafting step plus clarifying questions. Evidence for Phase 1 `gov rule`: turn an owner comment into a record PR, and ask back when the comment is ambiguous for a one-way decision.
- **Ruling PRs show the owner as author** because they were drafted through the owner's `gh` login. Fine while merge is the ratifying act, but a drafting App identity would keep authorship honest.
- **Model signatures disagree.** Planner signed `claude-opus-4-8[1m]`, builder `claude-opus-5-5`. Self-reported; the launcher should record the actual model before the committee diversity rule relies on it.
- **H5 first pass.** Told only "the questions on #2 have been resolved. Continue.", the builder found GOV-0002 and GOV-0003, revised PR #16 to match both, and cited them in the description. It also listed the calls it made that the rulings didn't cover (tracking-issue title, marker, comment format, close on stop). One data point; the real test is whether later questions cite them.
- **Schema accepted through a PR, not a question.** The event schema is a costly architecture decision, but the builder treated PR review as its ratification instead of opening a question. Borderline: merging is the owner's act either way, but the decision record trail skips it. Candidate rule: a PR that sets an interface other roles build on should say so in its description.
- **Auto mode blocked `gh pr edit` and `gh pr ready`** for the builder, leaving PR #16 a stale draft until the owner allowed them. Role sessions may need a narrow allowlist for their own PR housekeeping.

**Observations (2026-11-02, dashboard build)**

- **Comment rulings are the norm.** Of 7 questions, 2 have records (GOV-0002, GOV-0003). The other 5 were answered in one comment, within minutes, and closed with no record, including a one-way `external` decision (#33). The owner said narrow, temporary answers don't need records and that the convention should account for this later. Candidate: a lightweight "direction" outcome (comment + `gov:ruled-by-comment`, not precedent, TTL-bound), with a record still required for one-way or external decisions.
- **Questions are fast when the owner is present.** Median under 10 minutes for the last five, against 13 hours for the first two. The default action barely mattered; turnaround depends on the owner being around, not the process.
- **Merging approved undeclared calls.** PR #24's description listed three calls (reading shell commands in memory for PR/issue numbers, guessing the current issue from prompts, opt-in per machine). Merging approved them with no record. The first is an interpretation of a one-way security ruling (GOV-0002). Second time after #16; the builder now flags such calls well, but the PR is still where they get settled.
- **A session wrote governance practice into its own memory.** After #26, the builder saved a Claude Code memory note: owner-comment answers to narrow questions need no record and aren't precedent. It's accurate, but it's a rule about governance that lives outside the repo, unreviewed, visible only to sessions on this machine. Candidate rule: practice about governance goes in GOVERNANCE.md via PR, never in agent memory.
- **The builder asked well.** Five questions in about an hour, each with options, a default, and (for #31, #32) explicit precedent checks. #31 split a security sub-question out of a spend answer instead of acting on the owner's comment. Evidence for H1 and H5.
- **Only the builder has run.** No reviewer has reviewed a PR, so oversteps can only be found by the owner. H1 is untested from the reviewer side.
- **Visibility changed under existing rulings.** GOV-0002 and GOV-0003 were ruled while the repo was private. It is now public, so tracking-issue events (role, model, issue numbers, tool names, token counts) are public too. Raised as #36 rather than assumed.

Also note anything that **should** have been a question and wasn't (oversteps found in PR review). Those are the misses that a classifier can't learn from the issue list alone.

## Exit criteria (move to Phase 1 when all are true)

- At least 20 real questions logged across at least 4 domains.
- You can name the 3 shapes that cover most questions. Phase 1 automates those first.
- You've seen at least one committee and one lapse play out end to end.
- You've drafted a revised GOVERNANCE.md §2–§3 from what the log shows. Expect it to change, because the first taxonomy is a guess.

## What Phase 0 deliberately leaves out

There is no classifier, no automatic index regeneration, no Slack gateway, no agent notification on ruling, and no enforcement beyond CODEOWNERS. If you find yourself wanting one of these during Phase 0, note it in the log; that is evidence for the Phase 1 build order.
