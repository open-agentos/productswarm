---
id: GOV-0043
title: The Notion token is a 0600 file only `swarm specs` reads, and Ready means a feature's spec may be published
status: in-force
kind: ruling
question: "#943"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: external
  nature: values
  knowledge: held
decided_by: owner (mattmcalister), on #943
ratified_by: humans.owner
date: 2026-11-12
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - holding, reading or passing the Notion integration token
    - the `notion` backend of `swarm specs`
    - copying a Notion feature's spec text into a GitHub issue
---

## Ruling

The Notion integration token lives only in `~/.config/productswarm/notion.token` (0600) on the owner's machine, and only `swarm specs` reads it, at call time; never export it to an environment, and never pass or mount it in `swarm launch` or a container. Moving a feature to **Ready** in Notion is the owner's consent to publish that feature's spec in a public issue; `pull` reads only Ready features and copies nothing else.

## Applies when / does not apply when

- Applies when: a role or command needs the Notion token, or `swarm specs pull` copies spec text into an issue.
- Does not apply when: the token is for another service (this is not a general rule for outside-service tokens), or custody on the host, which is revisited with R4's `[specs]` trigger.

## Context

R2 and R3 of #937 §10, raised by the planner on #943 under Goal #938. The `notion` backend can't be built or run until custody and publishing are ruled. Both repos are public (GOV-0004), and a lead session can read anything in its own environment.

## Options considered

Part A (custody and scope):

1. **#937's default**: `NOTION_TOKEN` in the lead session's environment on the owner's machine and the host. The token is in a model's environment and in whatever it starts.
2. **A file only `swarm specs` reads, owner's machine only, until R4.** Chosen.
3. **A separate process holds the token.** Strongest, but new infrastructure before the first manual run; the owner wants it before the bridge runs unattended.
4. **The owner runs `swarm specs` by hand.** Brings back the hand-off #938 removes.

Part B (R3):

1. **Writing to the private workspace is not `external`, and Ready is consent to publish that feature's spec.** Chosen.
2. **All of it is `external`**, each pull and push needing approval.
3. **Issues carry only the feature ID and link.** Builders couldn't build without Notion access.

## Deliberation

n/a (authoritative). The owner ruled on #943: "Part A option 2 and Part B option 1, as recommended", with the details below.

## Consequences

- The token is read only by `swarm specs`, at call time, never exported to an environment.
- The host doesn't get the token. Custody is revisited with R4's `[specs]` trigger, which should take Part A option 3 (a separate process holds the token) before the bridge runs unattended.
- The `productswarm` integration gets Read content, Update content, Read comments and Insert comments; no Insert content and no user information. It is shared only with the "productswarm specs" page tree.
- Writing to the owner's private Notion workspace is not `external`. Draft features never leave Notion, and the bridge pulls nothing else. The owner has put this rule in the Features database's description.
- Cost: a lead session can still read the file with its shell, so the integration's scope, and the owner's one-click revocation in Notion, are the real limit.
- Revisit when R4's `[specs]` trigger is asked, or if the token is wanted for another service.

-- docs (claude-sonnet-5-5)
