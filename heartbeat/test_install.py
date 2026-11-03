"""Tests for heartbeat/install.py's settings helpers. Run: python3 -m unittest discover -s heartbeat"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install  # noqa: E402


class WithHooksTest(unittest.TestCase):
    BASE = {"permissions": {"allow": ["Bash(ls)"]},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]}}

    def test_adds_ours_at_the_given_path_and_keeps_the_rest(self):
        got = install.with_hooks(self.BASE, hook="/pinned/heartbeat/hook.py")
        self.assertEqual(got["permissions"], self.BASE["permissions"])
        self.assertEqual(got["hooks"]["Stop"][0], self.BASE["hooks"]["Stop"][0])
        self.assertEqual(got["hooks"]["Stop"][1]["hooks"][0]["command"],
                         'python3 -I "/pinned/heartbeat/hook.py" Stop')
        self.assertEqual(got["hooks"]["PostToolUse"][0]["matcher"], "*")
        self.assertEqual(sorted(got["hooks"]), sorted(install.EVENTS))

    def test_replaces_an_older_entry_instead_of_adding_a_second(self):
        once = install.with_hooks(self.BASE)                       # $CLAUDE_PROJECT_DIR, as before #93
        twice = install.with_hooks(once, hook="/pinned/heartbeat/hook.py")
        self.assertEqual(len(twice["hooks"]["SessionStart"]), 1)
        self.assertNotIn("CLAUDE_PROJECT_DIR", json.dumps(twice))

    def test_uninstall_removes_only_ours(self):
        got = install.with_hooks(install.with_hooks(self.BASE), uninstall=True)
        self.assertEqual(got, self.BASE)

    def test_does_not_modify_its_input(self):
        before = json.dumps(self.BASE)
        install.with_hooks(self.BASE)
        self.assertEqual(json.dumps(self.BASE), before)


class RefreshRuntimeTest(unittest.TestCase):
    def test_creates_then_moves_the_pinned_copy(self):
        import tempfile
        calls = []
        git = lambda args: (calls.append(args), (0, ""))[1]
        with tempfile.TemporaryDirectory() as tmp:
            rt = Path(tmp) / "runtime"
            self.assertEqual(install.refresh_runtime(Path("/repo"), rt, git), f"{rt}/heartbeat/hook.py")
            self.assertEqual(calls[-1], ["-C", "/repo", "worktree", "add", "-q", "--detach", str(rt), "origin/main"])
            rt.mkdir()
            (rt / ".git").write_text("gitdir: x\n")
            install.refresh_runtime(Path("/repo"), rt, git)
            self.assertEqual(calls[-1], ["-C", str(rt), "checkout", "-q", "--detach", "--force", "origin/main"])

    def test_git_failure_raises(self):
        with self.assertRaisesRegex(RuntimeError, "can't refresh the pinned hook copy"):
            install.refresh_runtime(Path("/repo"), Path("/nope/runtime"), lambda a: (1, "fatal"))


if __name__ == "__main__":
    unittest.main()
