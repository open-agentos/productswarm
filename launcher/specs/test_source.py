"""Tests for launcher/specs/source.py (#940): the SpecSource boundary and its model.

Run: python3 run_tests.py launcher
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs.source import (  # noqa: E402
    BRIDGE_STATUSES, Criterion, Feature, FeatureStatus, SchemaError, Spec, SpecSource,
    require_bridge_status,
)


class MiniSource:
    """The smallest in-memory source that keeps the protocol's contract."""

    name = "mini"
    simulated = True

    def __init__(self):
        self.status = {}
        self.links = {}
        self.comments = []

    def list_features(self, initiative_id):
        return []

    def get_spec(self, feature_id):
        return Spec()

    def set_status(self, feature_id, status, reason=None):
        self.status[feature_id] = (require_bridge_status(status), reason)

    def set_links(self, feature_id, issue_url=None, pr_url=None):
        self.links[feature_id] = (issue_url, pr_url)

    def comment(self, feature_id, body, marker):
        if any(f == feature_id and m == marker for f, _, m in self.comments):
            return False
        self.comments.append((feature_id, body, marker))
        return True


SECTIONS = {
    "Problem": "Owners can't see specs ship.",
    "Scope": "Pull Ready features into issues.",
    "Out of scope": "Writing spec bodies.",
    "Acceptance criteria": [("Pull opens one issue per Ready feature", False),
                            ("Push writes status back", True)],
    "Notes": "See #937.",
}


class StatusTest(unittest.TestCase):
    def test_names_match_notion_exactly(self):
        self.assertEqual([s.value for s in FeatureStatus],
                         ["Draft", "Ready", "In progress", "In review", "Shipped", "Blocked"])

    def test_bridge_statuses_are_the_four_after_ready(self):
        self.assertEqual({s.value for s in BRIDGE_STATUSES},
                         {"In progress", "In review", "Shipped", "Blocked"})

    def test_set_status_refuses_owner_statuses(self):
        src = MiniSource()
        for s in (FeatureStatus.DRAFT, FeatureStatus.READY, "Draft", "Ready", "Done"):
            with self.assertRaises(ValueError):
                src.set_status("FEAT-1", s)
        self.assertEqual(src.status, {})

    def test_set_status_accepts_bridge_statuses(self):
        src = MiniSource()
        src.set_status("FEAT-1", "In review")
        src.set_status("FEAT-2", FeatureStatus.BLOCKED, reason="issue closed unmerged")
        self.assertEqual(src.status["FEAT-1"][0], FeatureStatus.IN_REVIEW)
        self.assertEqual(src.status["FEAT-2"], (FeatureStatus.BLOCKED, "issue closed unmerged"))


class SpecHashTest(unittest.TestCase):
    def test_stable_across_key_order(self):
        a = Spec.from_sections(SECTIONS)
        b = Spec.from_sections(dict(reversed(list(SECTIONS.items()))))
        self.assertEqual(a.content_hash(), b.content_hash())
        self.assertEqual(len(a.content_hash()), 64)

    def test_stable_across_whitespace(self):
        messy = dict(SECTIONS)
        messy["Problem"] = "\n  \nOwners can't see specs ship.   \r\n\n"
        messy["Notes"] = "See #937.\t"
        messy["Acceptance criteria"] = [{"text": "Pull opens one issue per Ready feature  "},
                                        {"text": "Push writes status back", "checked": True}]
        self.assertEqual(Spec.from_sections(messy).content_hash(),
                         Spec.from_sections(SECTIONS).content_hash())

    def test_changes_when_any_section_changes(self):
        base = Spec.from_sections(SECTIONS).content_hash()
        for heading in ("Problem", "Scope", "Out of scope", "Notes"):
            changed = dict(SECTIONS, **{heading: SECTIONS[heading] + " More."})
            self.assertNotEqual(Spec.from_sections(changed).content_hash(), base, heading)
        for crit in ([("Pull opens one issue per Ready feature", True),
                      ("Push writes status back", True)],               # checked flag
                     [("Push writes status back", True),
                      ("Pull opens one issue per Ready feature", False)],  # order
                     SECTIONS["Acceptance criteria"][:1]):              # one removed
            changed = dict(SECTIONS, **{"Acceptance criteria": crit})
            self.assertNotEqual(Spec.from_sections(changed).content_hash(), base, crit)

    def test_unknown_heading_is_a_schema_error(self):
        with self.assertRaises(SchemaError):
            Spec.from_sections(dict(SECTIONS, Requirements="x"))


class PullableTest(unittest.TestCase):
    def test_pullable_with_criteria(self):
        self.assertEqual(Spec.from_sections(SECTIONS).pullable(), (True, None))

    def test_not_pullable_without_heading(self):
        sections = {k: v for k, v in SECTIONS.items() if k != "Acceptance criteria"}
        ok, reason = Spec.from_sections(sections).pullable()
        self.assertFalse(ok)
        self.assertIn("Acceptance criteria", reason)

    def test_not_pullable_when_empty(self):
        for crit in ([], [("   ", False)]):
            ok, reason = Spec.from_sections(dict(SECTIONS, **{"Acceptance criteria": crit})).pullable()
            self.assertFalse(ok)
            self.assertIn("empty", reason)


class ProtocolTest(unittest.TestCase):
    def test_minimal_source_satisfies_protocol(self):
        self.assertIsInstance(MiniSource(), SpecSource)

    def test_object_missing_a_method_does_not(self):
        class NoComment(MiniSource):
            comment = None
        self.assertNotIsInstance(object(), SpecSource)
        self.assertNotIsInstance(NoComment(), SpecSource)

    def test_comment_is_idempotent_by_marker(self):
        src = MiniSource()
        self.assertTrue(src.comment("FEAT-1", "shipped", "swarm:pr=12"))
        self.assertFalse(src.comment("FEAT-1", "shipped again", "swarm:pr=12"))
        self.assertEqual(len(src.comments), 1)

    def test_protocol_has_no_spec_body_writer(self):
        writers = {n for n in dir(SpecSource) if n.startswith(("set_", "write", "update"))}
        self.assertEqual(writers, {"set_status", "set_links"})

    def test_feature_model(self):
        f = Feature(id="FEAT-3", name="Pull", url="https://notion.so/x", initiative_id="init-1",
                    status=FeatureStatus.READY, last_edited="2026-11-12T09:00:00Z")
        self.assertIsNone(f.issue_url)
        self.assertEqual(f.status.value, "Ready")
        self.assertEqual(Criterion("x"), Criterion("x", False))


if __name__ == "__main__":
    unittest.main()
