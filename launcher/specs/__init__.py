"""The specs bridge (#937): specs written in a source such as Notion ship through the swarm.

`source.py` holds the `SpecSource` adapter boundary every backend implements (#937 §7).
`fake.py` is the `fake` backend over JSON fixtures (#941), for tests and simulated runs.
`snapshot.py` renders and reads the spec snapshot block in a feature's issue body (#953).
`events.py` is the append-only `events.jsonl` log of pulls, writes and decisions (#954).
`config.py` reads swarm.toml's `[specs]` table and builds the backend it names (#952).
`sync.py` is `swarm specs pull`: Ready features become sub-issues under the Goal (#955).
`drift.py` is `swarm specs diff`: specs edited since their snapshot, and the lead's decisions (#956).
"""
