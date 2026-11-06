# Example: tracking issue for one session

What [`session.jsonl`](session.jsonl) looks like on GitHub under GOV-0003: the same events with `prompt` removed, batched into comments.

## Issue

**Title:** `[heartbeat] builder 0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41`

**Body:**

```markdown
<!-- productswarm-heartbeat schema_version=1 session_id=0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41 -->
Heartbeat events for one builder session. Posted automatically; see heartbeat/SCHEMA.md.

-- builder (claude-opus-5-5)
```

## Comment 1

````markdown
builder session working on #2

```jsonl
{"schema_version":1,"ts":"2026-11-01T18:20:00Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"session_started","cost_usd":0,"token_counts":{"input":0,"output":0,"cache_read":0,"cache_creation":0}}
{"schema_version":1,"ts":"2026-11-01T18:20:02Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"prompt_submitted"}
{"schema_version":1,"ts":"2026-11-01T18:21:30Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"working_on","issue":2,"cost_usd":0.12,"token_counts":{"input":3100,"output":420,"cache_read":28000,"cache_creation":21000},"tools":["Bash"]}
```

-- builder (claude-opus-5-5)
````

## Comment 2

````markdown
builder opened PR #16 for #2

```jsonl
{"schema_version":1,"ts":"2026-11-01T18:26:30Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"heartbeat","issue":2,"cost_usd":0.71,"token_counts":{"input":18400,"output":5100,"cache_read":240000,"cache_creation":30000},"tools":["Bash","Write"]}
{"schema_version":1,"ts":"2026-11-01T18:42:10Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"pr_opened","issue":2,"pr":16,"cost_usd":1.84,"token_counts":{"input":41200,"output":9800,"cache_read":512000,"cache_creation":38000},"tools":["Bash","Write"]}
```

-- builder (claude-opus-5-5)
````

## Comment 3

````markdown
builder session working on #3

```jsonl
{"schema_version":1,"ts":"2026-11-01T18:44:00Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"working_on","issue":3,"cost_usd":1.9,"token_counts":{"input":42000,"output":10100,"cache_read":530000,"cache_creation":38000},"tools":["Bash"]}
{"schema_version":1,"ts":"2026-11-01T18:47:20Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"blocked","issue":3,"gov_question":15,"cost_usd":2.05,"token_counts":{"input":44800,"output":11000,"cache_read":561000,"cache_creation":39000},"tools":["Bash"]}
{"schema_version":1,"ts":"2026-11-01T18:48:00Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"stopped","cost_usd":2.07,"token_counts":{"input":45100,"output":11200,"cache_read":566000,"cache_creation":39000}}
```

-- builder (claude-opus-5-5)
````

Comments 1 to 3 start with a line naming the issue, so issues #2 and #3 show a "mentioned this" reference to this tracking issue. The issue is closed after comment 3, which carries the `stopped` event.
