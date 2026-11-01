#!/usr/bin/env bash
# Create the gov: labels in a repo. Run once:  ./governance/setup-labels.sh owner/repo
# Uses the gov: prefix so nothing collides with AgentOS status: labels (which auto-dispatch agents).
set -euo pipefail
REPO="${1:?usage: setup-labels.sh owner/repo}"

label() { gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force; }

# lifecycle
label "gov:question"      "5319e7" "A decision that needs a ruling (GOVERNANCE.md §4)"
label "gov:deliberating"  "1d76db" "Advice, consent, committee or vote in progress"
label "gov:awaiting-ruling" "fbca04" "Deliberation done; waiting for owner or ratifier"
label "gov:ruled"         "0e8a16" "Ruling merged; see the GOV-NNNN record"
label "gov:lapsed"        "d4c5f9" "TTL passed without a ruling; default stood; not precedent"
label "gov:called-in"     "b60205" "A human has taken this question over; agents stop deliberating"
label "gov:blocking"      "d93f0b" "An agent has stopped work waiting on this"

# shapes (set by whoever classifies; Phase 0 = the asker, corrected by a human)
for s in authoritative empirical advice consent committee vote; do
  label "gov:shape/$s" "c5def5" "Decision shape: $s"
done

# Phase 0 research tag
label "gov:misclassified" "e99695" "The asker's classification or shape was wrong; note why in a comment"
