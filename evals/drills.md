# Drills

Scripted drills in `open-agentos/productswarm-scratch` that show a capability on purpose instead of waiting for it by chance. Each section records one drill run: what happened, with links, and the owner's acts as `swarm acts` counts them.

## M4 scripted drill (#894)

Serves M4 (#686), criteria 2 to 4. Plan and Goal text: [#894](https://github.com/open-agentos/productswarm/issues/894#issuecomment-6825116062).

**Goal:** [scratch#5](https://github.com/open-agentos/productswarm-scratch/issues/5) · **Ran:** 2026-11-12, from 13:54 UTC · **Result:** _pending_

| # | Event | What happened | Links |
|---|---|---|---|
| 1 | The owner opens a Goal in the scratch repo | The owner opened the Goal at 13:54 UTC with the text posted on #894. The builder then opened its 4 Tasks as sub-issues (#6; #7 and #8 blocked by #6 only; #9 blocked by #8), so they are go under GOV-0031 with no `ready` | [scratch#5](https://github.com/open-agentos/productswarm-scratch/issues/5), [#6](https://github.com/open-agentos/productswarm-scratch/issues/6), [#7](https://github.com/open-agentos/productswarm-scratch/issues/7), [#8](https://github.com/open-agentos/productswarm-scratch/issues/8), [#9](https://github.com/open-agentos/productswarm-scratch/issues/9) |
| 2 | Several Tasks under it built, reviewed and merged by the merger | 3 Tasks built by `swarm watch`-started builders, approved by the reviewer at head and merged by the merger under the standing grant (GOV-0027): #6 (opened 13:58, merged 14:50), #7 (opened 15:49, merged ~16:08), #8 (merged 16:20). The merges didn't close their issues: the owner closed #6 at 15:45 and #7 and #8 at 17:02 by hand (#812). #7 and #8 waited about an hour for #6 to close, because they were blocked by it | [PR #11](https://github.com/open-agentos/productswarm-scratch/pull/11), [PR #15](https://github.com/open-agentos/productswarm-scratch/pull/15), [PR #16](https://github.com/open-agentos/productswarm-scratch/pull/16) |
| 3 | A planted defect the reviewer catches (gate 13, GOV-0021, GOV-0037) | _pending_ | |
| 4 | A changes-requested loop on a PR the builder didn't write, fixed with no hand start (#738) | _pending_ | |
| 5 | A merge conflict fixed with no hand start (#893) | After PR #15 merged, PR #16 went `CONFLICTING` (seen 16:08). Its builder pushed a merge of `main` at 16:11 (`ec3d836`). The reviewer approved the new head at 16:17, and the merger merged it at 16:20. Nobody started that run by hand | [PR #16](https://github.com/open-agentos/productswarm-scratch/pull/16) |
| 6 | One protected-path PR, merged on the owner's approval at head (GOV-0027) | _pending_ | |
| 7 | One `gov:question`, answered by the owner | At 17:06 a builder declined #9 as not go: it read the drill link (#894) as the parent instead of the sub-issue parent #5. The #894 builder opened the dependency question #936 at ~18:00 and corrected the reading on #9. Answer: _pending_ | [#936](https://github.com/open-agentos/productswarm/issues/936), [#9 refusal](https://github.com/open-agentos/productswarm-scratch/issues/9) |
| 8 | The scratch repo paused alone while productswarm keeps working (gate 19, #892) | _pending_ | |
| 9 | The owner's acts counted by `swarm acts` | _pending_ | |

### Owner's acts (`swarm acts`)

_pending_
