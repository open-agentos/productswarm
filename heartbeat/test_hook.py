"""Tests for heartbeat/hook.py. Run: python3 -m unittest discover -s heartbeat

Uses a fake `gh` on PATH that records its calls, so nothing touches GitHub.
If `jsonschema` happens to be installed, events are also checked against
event.schema.json; it is not a dependency.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE / "hook.py"
SID = "11111111-2222-3333-4444-555555555555"
REPO = "open-agentos/productswarm"

sys.path.insert(0, str(HERE))
import hook  # noqa: E402

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_GH_LOG"]
with open(log, "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "stdin": "" if sys.stdin.isatty() else sys.stdin.read()}) + "\n")
if os.environ.get("FAKE_GH_FAIL"):
    print("boom", file=sys.stderr); sys.exit(1)
a = sys.argv[1:]
if a[:2] == ["issue", "create"]:
    print("https://github.com/open-agentos/productswarm/issues/99")
elif a[:2] == ["pr", "view"]:
    print("3")
"""


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bindir = self.tmp / "bin"
        bindir.mkdir()
        gh = bindir / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin",
                        f"https://github.com/{REPO}.git"], check=True)
        self.transcript = self.tmp / "t.jsonl"
        self.transcript.write_text("")
        self.env = {
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "PRODUCTSWARM_HOME": str(self.tmp / "home"),
            "SWARM_ROLE": "builder",
            "FAKE_GH_LOG": str(self.tmp / "gh.log"),
            "HEARTBEAT_SYNC_FLUSH": "1",
        }

    def run_hook(self, event, **payload):
        p = {"session_id": SID, "transcript_path": str(self.transcript), "cwd": str(self.repo),
             "hook_event_name": event, **payload}
        r = subprocess.run([sys.executable, "-I", str(HOOK), event], input=json.dumps(p),
                           capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "", "hook must not print to stdout")
        return r

    def add_usage(self, msg_id, inp, out, model="claude-opus-5-5"):
        with open(self.transcript, "a") as f:
            f.write(json.dumps({"type": "assistant", "message": {"id": msg_id, "model": model, "usage": {
                "input_tokens": inp, "output_tokens": out,
                "cache_read_input_tokens": 10, "cache_creation_input_tokens": 1}}}) + "\n")

    def spool(self, sid=SID):
        p = self.tmp / "home" / "events" / f"{sid}.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def gh_calls(self):
        p = self.tmp / "gh.log"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def remote_events(self):
        out = []
        for c in self.gh_calls():
            if c["argv"][:2] == ["issue", "comment"]:
                block = c["stdin"].split("```jsonl\n", 1)[1].split("\n```", 1)[0]
                out += [json.loads(l) for l in block.splitlines()]
        return out

    def full_session(self):
        self.run_hook("SessionStart", source="startup", model="claude-opus-5-5")
        self.add_usage("m1", 100, 5)
        self.add_usage("m1", 100, 50)          # streaming repeat of the same message
        self.run_hook("UserPromptSubmit",
                      prompt="Start on issue 3. token ghp_abcdefghijklmnopqrstuvwxyz0123 API_KEY=hunter2 " + "x" * 3000)
        self.add_usage("m2", 7, 3)
        self.run_hook("PostToolUse", tool_name="Read", tool_input={"file_path": "/secret/path.txt"},
                      tool_response={"content": "file body"})
        self.run_hook("PostToolUse", tool_name="Bash",
                      tool_input={"command": "gh pr create --title X --body-file /tmp/body.md"},
                      tool_response={"stdout": f"https://github.com/{REPO}/pull/21\n", "stderr": ""})
        self.run_hook("Stop")
        self.run_hook("SessionEnd", reason="exit")

    def test_full_session(self):
        self.full_session()
        events = self.spool()
        self.assertEqual([e["event"] for e in events],
                         ["session_started", "prompt_submitted", "working_on", "pr_opened", "stopped"])
        prompt = events[1]["prompt"]
        self.assertLessEqual(len(prompt), 2000)
        self.assertNotIn("ghp_abcdef", prompt)
        self.assertNotIn("hunter2", prompt)
        self.assertEqual(events[2]["issue"], 3)
        self.assertEqual((events[3]["pr"], events[3]["issue"]), (21, 3))
        self.assertEqual(events[3]["tools"], ["Read", "Bash"])
        self.assertEqual(events[-1]["token_counts"],
                         {"input": 107, "output": 53, "cache_read": 20, "cache_creation": 2})
        self.assertEqual(events[0]["model"], "claude-opus-5-5")

        calls = self.gh_calls()
        self.assertEqual(calls[0]["argv"][:2], ["issue", "create"])
        self.assertEqual(calls[0]["argv"][calls[0]["argv"].index("--title") + 1], f"[heartbeat] builder {SID}")
        self.assertIn(f"session_id={SID}", calls[0]["stdin"])
        self.assertNotIn("--label", calls[0]["argv"])
        self.assertEqual(calls[-1]["argv"][:3], ["issue", "close", "99"])
        remote = self.remote_events()
        self.assertEqual([e["event"] for e in remote], [e["event"] for e in events])
        self.assertTrue(all("prompt" not in e for e in remote))
        for c in calls:
            self.assertTrue(c["stdin"].rstrip().endswith("-- builder (claude-opus-5-5)") or not c["stdin"])

    def test_nothing_sensitive_leaves_tool_calls(self):
        self.full_session()
        everything = "".join(p.read_text() for p in (self.tmp / "home").rglob("*") if p.is_file())
        everything += (self.tmp / "gh.log").read_text()
        for needle in ("/secret/path.txt", "file body", "--body-file /tmp/body.md", "hunter2", "ghp_abcdef"):
            self.assertNotIn(needle, everything)

    def test_events_match_schema(self):
        try:
            import jsonschema
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema not installed")
        self.full_session()
        schema = json.loads((HERE / "event.schema.json").read_text())
        V = jsonschema.Draft202012Validator
        reg = Registry().with_resource(schema["$id"], Resource.from_contents(schema))
        local, remote = V(schema), V({"$ref": schema["$id"] + "#/$defs/remote"}, registry=reg)
        for e in self.spool():
            self.assertEqual(list(local.iter_errors(e)), [], e)
        for e in self.remote_events():
            self.assertEqual(list(remote.iter_errors(e)), [], e)

    def test_no_role_means_no_op(self):
        del self.env["SWARM_ROLE"]
        self.run_hook("SessionStart", source="startup")
        self.assertFalse((self.tmp / "home").exists())
        self.assertEqual(self.gh_calls(), [])

    def test_gh_failure_keeps_events_for_retry(self):
        self.env["FAKE_GH_FAIL"] = "1"
        self.run_hook("SessionStart", source="startup")
        sending = self.tmp / "home" / "outbox" / f"{SID}.sending.jsonl"
        self.assertTrue(sending.exists())
        self.assertIn("gh issue create failed", (self.tmp / "home" / "heartbeat.log").read_text())
        del self.env["FAKE_GH_FAIL"]
        self.run_hook("SessionEnd", reason="exit")
        self.assertEqual([e["event"] for e in self.remote_events()], ["session_started", "stopped"])
        self.assertFalse(sending.exists())

    def test_blocking_gov_question_and_emit(self):
        self.run_hook("SessionStart", source="startup")
        self.run_hook("PostToolUse", tool_name="Bash",
                      tool_input={"command": "gh issue create --title 'GOV-Q: x' --label gov:question --label gov:blocking"},
                      tool_response={"stdout": f"https://github.com/{REPO}/issues/15\n"})
        r = subprocess.run([sys.executable, "-I", str(HOOK), "emit", "working_on", "--issue", "4"],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        events = self.spool()
        self.assertEqual(events[1]["event"], "blocked")
        self.assertEqual(events[1]["gov_question"], 15)
        self.assertEqual((events[2]["event"], events[2]["issue"]), ("working_on", 4))

    def comments(self):
        return [c["stdin"] for c in self.gh_calls() if c["argv"][:2] == ["issue", "comment"]]

    def test_comments_name_the_issue_for_its_timeline(self):
        self.full_session()
        bodies = self.comments()
        named = [l for b in bodies for l in b.split("```jsonl", 1)[0].splitlines() if l.strip()]
        self.assertEqual(named, ["builder session working on #3", "builder opened PR #21 for #3"])
        for b in bodies:                        # the prose stays above the fence
            self.assertTrue(b.startswith("```jsonl") or b.split("\n\n", 1)[1].startswith("```jsonl"), b)

    def test_working_on_is_named_once_per_issue(self):
        def emit(issue):
            r = subprocess.run([sys.executable, "-I", str(HOOK), "emit", "working_on", "--issue", str(issue)],
                               capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.run_hook("SessionStart", source="startup")
        for issue in (4, 5, 4):
            emit(issue)
        named = [b.split("```jsonl", 1)[0].strip() for b in self.comments()]
        self.assertEqual([n for n in named if n],
                         ["builder session working on #4", "builder session working on #5"])
        self.assertEqual([e["issue"] for e in self.remote_events() if e["event"] == "working_on"], [4, 5, 4])

    def test_failed_post_names_the_issue_on_retry(self):
        self.run_hook("SessionStart", source="startup")
        self.env["FAKE_GH_FAIL"] = "1"
        subprocess.run([sys.executable, "-I", str(HOOK), "emit", "working_on", "--issue", "4"], env=self.env)
        del self.env["FAKE_GH_FAIL"]
        failed = len(self.comments())           # the fake gh logs the failed attempt too
        self.run_hook("SessionEnd", reason="exit")
        named = [b.split("```jsonl", 1)[0].strip() for b in self.comments()[failed:]]
        self.assertEqual([n for n in named if n], ["builder session working on #4"])

    def test_dashboard_still_parses_named_comments(self):
        sys.path.insert(0, str(HERE.parent / "dashboard"))
        import generate
        self.full_session()
        parsed = [e for b in self.comments() for e in generate.parse_comment(b)]
        self.assertEqual(parsed, self.remote_events())
        self.assertEqual([e["event"] for e in parsed],
                         ["session_started", "prompt_submitted", "working_on", "pr_opened", "stopped"])

    def test_resume_after_stop_reopens(self):
        self.run_hook("SessionStart", source="startup")
        self.run_hook("SessionEnd", reason="exit")
        self.run_hook("SessionStart", source="resume")
        self.assertEqual([e["event"] for e in self.spool()], ["session_started", "stopped", "session_started"])
        self.assertEqual(self.gh_calls()[-1]["argv"][:3], ["issue", "reopen", "99"])
        self.assertEqual(sum(c["argv"][:2] == ["issue", "create"] for c in self.gh_calls()), 1)

    # A session whose window was closed: SessionEnd never runs (#75).
    GONE = "99999999-8888-7777-6666-555555555555"

    def vanish(self, sid, silent_for=0, role="builder", launcher=False):
        """Start a session as `role`, then leave it without SessionEnd, `silent_for` seconds ago."""
        env = self.env
        self.env = {**env, "SWARM_ROLE": role}
        self.run_hook("SessionStart", session_id=sid, source="startup")
        self.run_hook("UserPromptSubmit", session_id=sid, prompt="work on issue 7")
        self.env = env
        p = self.tmp / "home" / "state" / f"{sid}.json"
        state = json.loads(p.read_text())
        state["last_event_at"] -= silent_for
        p.write_text(json.dumps(state))
        if launcher:
            pid = self.tmp / "home" / "launcher" / f"{sid}.pid"
            pid.parent.mkdir(parents=True, exist_ok=True)
            pid.write_text("4242\n")

    def closes(self):
        return [c["argv"][2] for c in self.gh_calls() if c["argv"][:2] == ["issue", "close"]]

    def test_next_session_stops_a_silent_vanished_session(self):
        self.vanish(self.GONE, silent_for=hook.STALE_AFTER + 60)
        self.run_hook("SessionStart", source="startup")
        gone = self.spool(self.GONE)
        self.assertEqual([e["event"] for e in gone], ["session_started", "prompt_submitted", "working_on", "stopped"])
        self.assertEqual(gone[-1]["issue"], 7)
        self.assertEqual(self.closes(), ["99"])
        self.assertTrue(json.loads((self.tmp / "home" / "state" / f"{self.GONE}.json").read_text())["stopped"])
        self.assertEqual([e["event"] for e in self.spool()], ["session_started"])   # the new one is untouched

    def test_launcher_session_whose_process_is_gone_stops_at_once(self):
        self.vanish(self.GONE, launcher=True)
        self.run_hook("SessionStart", source="startup")
        self.assertEqual(self.spool(self.GONE)[-1]["event"], "stopped")
        self.assertEqual(self.closes(), ["99"])

    def test_recently_active_session_is_left_alone(self):
        self.vanish(self.GONE, silent_for=60)
        self.run_hook("SessionStart", source="startup")
        self.assertNotEqual(self.spool(self.GONE)[-1]["event"], "stopped")
        self.assertEqual(self.closes(), [])

    def test_running_process_is_left_alone_however_silent(self):
        self.vanish(self.GONE, silent_for=hook.STALE_AFTER * 10, launcher=True)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "--session-id", self.GONE])
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        self.run_hook("SessionStart", source="startup")
        self.assertNotEqual(self.spool(self.GONE)[-1]["event"], "stopped")
        self.assertEqual(self.closes(), [])

    def test_other_roles_are_left_alone(self):
        # The dashboard takes a session's events only from its own role's App.
        self.vanish(self.GONE, silent_for=hook.STALE_AFTER + 60, role="planner")
        self.run_hook("SessionStart", source="startup")
        self.assertNotEqual(self.spool(self.GONE)[-1]["event"], "stopped")

    def test_swept_session_that_comes_back_reopens(self):
        self.vanish(self.GONE, silent_for=hook.STALE_AFTER + 60)
        self.run_hook("SessionStart", source="startup")
        self.run_hook("UserPromptSubmit", session_id=self.GONE, prompt="still here")
        self.assertEqual([e["event"] for e in self.spool(self.GONE)][-3:],
                         ["stopped", "session_started", "prompt_submitted"])
        self.assertEqual(self.gh_calls()[-1]["argv"][:3], ["issue", "reopen", "99"])

    def test_sweep_by_hand(self):
        self.vanish(self.GONE, silent_for=hook.STALE_AFTER + 60)
        r = subprocess.run([sys.executable, "-I", str(HOOK), "sweep"], capture_output=True, text=True,
                           env=self.env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"stopped: {self.GONE}", r.stderr)
        self.assertEqual(self.closes(), ["99"])


class RedactionTest(unittest.TestCase):
    def test_patterns(self):
        cases = {
            "ghs_ABCDEFGHIJKLMNOPQRSTUV1234": "[REDACTED]",
            "github_pat_11ABCDEFG0123456789_abcdef": "[REDACTED]",
            "sk-ant-api03-abcdefghijklmnopqrstu": "[REDACTED]",
            "export GITHUB_TOKEN=abc123": "export GITHUB_TOKEN=[REDACTED]",
            'db_password = "p a s s"': "db_password = [REDACTED]",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----": "[REDACTED PEM]",
            "-----BEGIN PRIVATE KEY-----\nMIIE truncated": "[REDACTED PEM]",
            "work on issue 3": "work on issue 3",
        }
        for raw, want in cases.items():
            self.assertEqual(hook.redact(raw), want, raw)

    def test_truncates_after_redacting(self):
        out = hook.clean_prompt("x" * 1995 + " ghp_ABCDEFGHIJKLMNOPQRSTUV1234")
        self.assertEqual(len(out), 2000)
        self.assertNotIn("ghp_", out)


if __name__ == "__main__":
    unittest.main()
