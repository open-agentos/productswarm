#!/usr/bin/env python3
"""Run every test_*.py under launcher/, dashboard/, evals/, heartbeat/ and classify/ (#521, #1010).

This is the test check GOV-0022 stage 1 needs: `.github/workflows/tests.yml` runs it on
every pull request to main. Each directory runs in its own process, from inside that
directory, because its tests import their siblings by bare name (`import swarm`,
`import generate`) and two directories may share a module name.

Usage: python3 run_tests.py [dir ...]   (default: all five)
Exits 0 only if every directory's tests pass and at least one test ran in each.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIRS = ("launcher", "dashboard", "evals", "heartbeat", "classify")


def run(name: str) -> bool:
    d = ROOT / name
    if not any(d.glob("test_*.py")):
        print(f"run_tests: {name}/ has no test_*.py", flush=True)
        return False
    print(f"== {name}/", flush=True)
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
        cwd=d,
    )
    return r.returncode == 0


def main(argv: list[str]) -> int:
    names = argv or list(DIRS)
    unknown = [n for n in names if n not in DIRS]
    if unknown:
        print(f"run_tests: unknown dir {', '.join(unknown)}; choose from {', '.join(DIRS)}")
        return 2
    failed = [n for n in names if not run(n)]
    if failed:
        print(f"run_tests: FAILED in {', '.join(failed)}")
        return 1
    print(f"run_tests: OK ({', '.join(names)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
