#!/usr/bin/env python
# Cross-platform task runner. Works on Windows, macOS and Linux with no `make`.
# OWNER: Arash.
#
#   python run.py            list tasks
#   python run.py mocks      generate synthetic data  <- start here
#   python run.py test       run the test suite
#   python run.py app        launch the dashboard
#   python run.py all        full pipeline
#
# Why not a Makefile: `make` is not installed on Windows by default, and half of
# this team is on Windows. One runner that works everywhere beats two that do not.

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

TASKS: dict[str, tuple[str, list[list[str]]]] = {
    "mocks": ("generate schema-valid synthetic data (start here)",
              [[sys.executable, "scripts/make_mocks.py"]]),
    "fetch": ("L1 pull + cache all real sources          [Jean]",
              [[sys.executable, "-m", "ethack.sources.epa"],
               [sys.executable, "-m", "ethack.sources.sec"],
               [sys.executable, "-m", "ethack.sources.ex21"],
               [sys.executable, "-m", "ethack.sources.echo"],
               [sys.executable, "-m", "ethack.sources.satellite"]]),
    "link": ("L2 facility -> ticker resolution          [Arash]",
             [[sys.executable, "-m", "ethack.link"]]),
    "score": ("L3+L4 indicators and scores               [Lauren]",
              [[sys.executable, "-m", "ethack.score"]]),
    "portfolio": ("L5 build the $1B book                     [Florian]",
                  [[sys.executable, "-m", "ethack.portfolio.construct"]]),
    "eval": ("L6 validation + METRICS.md                [Harprit]",
             [[sys.executable, "-m", "ethack.eval.validate"]]),
    "app": ("launch the dashboard",
            [[sys.executable, "-m", "streamlit", "run", "app/main.py"]]),
    "test": ("pytest (network tests skipped)",
             [[sys.executable, "-m", "pytest", "-q", "-m", "not network"]]),
    "fmt": ("format + autofix with ruff",
            [[sys.executable, "-m", "ruff", "format", "src", "app", "tests", "scripts"],
             [sys.executable, "-m", "ruff", "check", "--fix",
              "src", "app", "tests", "scripts"]]),
    "doctor": ("check your environment is set up correctly",
               [[sys.executable, "scripts/doctor.py"]]),
    # --- git workflow (see CONVENTIONS.md). Dispatched specially below. ---
    "sync": ("pull main before you branch", []),
    "ship": ("rebase, test, ff-only merge into main, push   (ship <branch>)", []),
    "progress": ("print a PROGRESS.md entry stub", []),
}

GIT_TASKS = {"sync", "ship", "progress"}

PIPELINE = ["mocks", "link", "score", "portfolio", "eval"]


def env() -> dict[str, str]:
    e = os.environ.copy()
    existing = e.get("PYTHONPATH", "")
    e["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    return e


def run(task: str) -> int:
    label, cmds = TASKS[task]
    for cmd in cmds:
        print(f"\n>>> {' '.join(str(c) for c in cmd)}", flush=True)
        rc = subprocess.call(cmd, cwd=ROOT, env=env())
        if rc != 0:
            print(f"\n!!! task '{task}' failed (exit {rc})", file=sys.stderr)
            return rc
    return 0


def git(*args: str, check: bool = True) -> int:
    print(f"\n>>> git {' '.join(args)}", flush=True)
    rc = subprocess.call(["git", *args], cwd=ROOT)
    if rc != 0 and check:
        raise SystemExit(f"\n!!! git {' '.join(args)} failed (exit {rc})")
    return rc


def task_sync() -> int:
    git("switch", "main")
    git("pull", "--rebase", "origin", "main")
    print("\nmain is current. now: git switch -c <yourname>/<thing>")
    return 0


def task_ship(branch: str | None) -> int:
    if not branch:
        cur = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
        if cur and cur != "main":
            branch = cur
            print(f"(no branch given, using current branch: {branch})")
        else:
            print("usage: python run.py ship <yourname>/<thing>", file=sys.stderr)
            return 2

    git("switch", branch)
    git("pull", "--rebase", "origin", "main")
    if run("test") != 0:
        print("\n!!! tests fail on top of main. fix before shipping.", file=sys.stderr)
        return 1
    git("switch", "main")
    git("pull", "--rebase", "origin", "main")
    if git("merge", "--ff-only", branch, check=False) != 0:
        print("\n--ff-only refused: someone pushed while you were testing.\n"
              "That is the check working, not an error. Do:\n"
              f"  git switch {branch}\n"
              "  git pull --rebase origin main\n"
              "  python run.py test\n"
              f"  python run.py ship {branch}", file=sys.stderr)
        return 1
    git("push", "origin", "main")
    git("branch", "-d", branch, check=False)
    print(f"\nmerged {branch} into main. did you log it in PROGRESS.md?")
    return 0


def task_progress() -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip() or "main"
    print(f"""
### {now} UTC - {branch}
- **Shipped:**
- **Next:**
- **Blocked:** none
- **Needs from others:**
""")
    print("(paste that at the END of your own section in PROGRESS.md)")
    return 0


def usage() -> None:
    print("usage: python run.py <task>\n")
    width = max(len(t) for t in TASKS)
    for name, (label, _) in TASKS.items():
        if name in GIT_TASKS:
            continue
        print(f"  {name:<{width}}  {label}")
    print()
    for name in ("sync", "ship", "progress"):
        print(f"  {name:<{width}}  {TASKS[name][0]}")
    print(f"  {'all':<{width}}  {' -> '.join(PIPELINE)}")
    print("\nNew here? Run:  python run.py mocks   then   python run.py test")


def main() -> int:
    if len(sys.argv) < 2:
        usage()
        return 0
    task = sys.argv[1]
    if task in GIT_TASKS:
        if task == "sync":
            return task_sync()
        if task == "progress":
            return task_progress()
        return task_ship(sys.argv[2] if len(sys.argv) > 2 else None)
    if task == "all":
        for t in PIPELINE:
            if (rc := run(t)) != 0:
                return rc
        print("\npipeline complete")
        return 0
    if task not in TASKS:
        print(f"unknown task {task!r}\n", file=sys.stderr)
        usage()
        return 2
    return run(task)


if __name__ == "__main__":
    sys.exit(main())
