"""The specs bridge (#937): specs written in a source such as Notion ship through the swarm.

`source.py` holds the `SpecSource` adapter boundary every backend implements (#937 §7).
`events.py` is the append-only `events.jsonl` log of pulls, writes and decisions (#954).
"""
