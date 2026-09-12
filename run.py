"""One entry point for everything. Run from the repo root.

    python run.py setup                          once per laptop
    python run.py start                          before you work: pull + show status
    python run.py save "[social] what I did"     commit + pull + check + push
    python run.py status                         what is changed / unpushed
    python run.py check                          format check + tests
    python run.py new-indicator social pay_ratio create catalog row + script
    python run.py build social [indicator_id]    run the scripts -> indicators/*.csv
    python run.py score [profile]                scores 0-100 for a profile -> scores/<profile>/
    python run.py dashboard                      open the dashboard in the browser
"""

from __future__ import annotations

import csv
import runpy
import shutil
import subprocess
import sys
import traceback

from common.config import (
    CATALOG_COLUMNS,
    CATEGORIES,
    MAX_FILE_MB,
    ROOT,
    catalog_path,
    scripts_dir,
)

BRANCH = "main"

OWNERS = {
    "economic": "Lauren",
    "social": "Florian + Lauren + Arash (one indicator = one person, see social/catalog.csv)",
    "environmental": "Jean",
    "universe": "Arash",
    "portfolio": "Arash",
    "profiles": "Arash",
    "dashboard": "Arash",
    "common": "Arash",
    "tests": "Arash",
}


# ---------------------------------------------------------------- helpers
def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def git_lines(*args: str) -> list[str]:
    return [line for line in git(*args).stdout.splitlines() if line.strip()]


def owner_of(path: str) -> str:
    parts = path.split("/")
    if parts[0] == "docs" and len(parts) == 3 and parts[1] == "tasks":
        return parts[2].removesuffix(".md").capitalize()
    return OWNERS.get(parts[0], "Arash (repo setup)")


def say(msg: str = "") -> None:
    print(msg, flush=True)


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def require_main() -> bool:
    branch = current_branch()
    if branch != BRANCH:
        say(f"STOP: you are on branch '{branch}', this team works on '{BRANCH}'.")
        say(f"      Ask Arash before switching - uncommitted work could get mixed up.")
        return False
    return True


def rebase_in_progress() -> bool:
    git_dir = ROOT / ".git"
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


# ---------------------------------------------------------------- git flow
def sync() -> bool:
    """Pull the team's latest work and replay local commits on top. Never loses work."""
    if rebase_in_progress():
        say("STOP: a previous pull was interrupted. Ask Arash - do not run git commands to 'fix' it.")
        return False
    say("pulling latest work from GitHub ...")
    result = git("pull", "--rebase", "--autostash", "origin", BRANCH)
    if result.returncode == 0:
        say("  up to date with the team")
        return True

    conflicts = git_lines("diff", "--name-only", "--diff-filter=U")
    if rebase_in_progress():
        git("rebase", "--abort")
    say("")
    say("STOP: your changes clash with a teammate's changes. Nothing was lost -")
    say("      your commits and files are exactly as they were before the pull.")
    for path in conflicts:
        say(f"      conflict in {path}  (owner: {owner_of(path)})")
    if not conflicts:
        say(result.stderr.strip())
    say("      Tell the owner / Arash which file. Do NOT force-push or reset.")
    return False


def cmd_start() -> int:
    if not require_main() or not sync():
        return 1
    return cmd_status()


def cmd_status() -> int:
    git("fetch", "-q", "origin", BRANCH)
    say(f"branch: {current_branch()}")
    changed = git_lines("status", "--short")
    say(f"uncommitted changes: {len(changed)}")
    for line in changed[:30]:
        say(f"  {line}")
    ahead = git("rev-list", "--count", f"origin/{BRANCH}..HEAD").stdout.strip() or "?"
    behind = git("rev-list", "--count", f"HEAD..origin/{BRANCH}").stdout.strip() or "?"
    say(f"commits not pushed yet: {ahead}")
    say(f"team commits you have not pulled: {behind}")
    return 0


def cmd_save(message: str) -> int:
    if not require_main():
        return 1
    if rebase_in_progress():
        say("STOP: a previous pull was interrupted. Ask Arash.")
        return 1

    git("add", "-A")
    staged = git_lines("diff", "--cached", "--name-only")
    blocked = [p for p in staged if p.split("/")[-1] == ".env"]
    too_big = [
        p for p in staged
        if (ROOT / p).is_file() and (ROOT / p).stat().st_size > MAX_FILE_MB * 1024 * 1024
    ]
    if blocked or too_big:
        git("reset", "-q")
        for p in blocked:
            say(f"STOP: {p} contains secrets and must never be committed.")
        for p in too_big:
            say(f"STOP: {p} is larger than {MAX_FILE_MB} MB. Add it to .gitignore and commit the")
            say(f"      download script instead, so others can recreate it.")
        return 1

    if staged:
        say("committing:")
        for p in staged:
            say(f"  {p}   (owner: {owner_of(p)})")
        if not message.lstrip().startswith("["):
            areas = {p.split("/")[0] for p in staged}
            message = f"[{areas.pop() if len(areas) == 1 else 'misc'}] {message}"
        result = git("commit", "-q", "-m", message)
        if result.returncode != 0:
            say(result.stdout + result.stderr)
            return 1

    if not sync():
        return 1

    ahead = int(git("rev-list", "--count", f"origin/{BRANCH}..HEAD").stdout.strip() or 0)
    if ahead == 0:
        say("nothing new to push - everything is already on GitHub")
        return 0

    changed = git_lines("diff", "--name-only", f"origin/{BRANCH}..HEAD")
    if not checks_pass_for(changed):
        say("NOT PUSHED: fix the errors above, then run save again.")
        say("            Your commit is safe locally.")
        return 1

    for attempt in range(2):
        result = git("push", "origin", BRANCH)
        if result.returncode == 0:
            say(f"saved and pushed {ahead} commit(s) to GitHub")
            return 0
        if attempt == 0 and not sync():  # someone pushed in the last seconds
            return 1
    say("push failed:\n" + result.stderr)
    return 1


def checks_pass_for(changed: list[str]) -> bool:
    """Only errors in areas you changed block your push - a teammate's broken file never blocks you."""
    from common.validate import print_report, validate_all

    areas = {p.split("/")[0] for p in changed}
    report = validate_all()
    mine = [(a, m) for a, m in report.errors if a.split("/")[0] in areas]
    others = [(a, m) for a, m in report.errors if a.split("/")[0] not in areas]
    for area, msg in others:
        say(f"  (not yours, not blocking) {area}: {msg}")
    ok = True
    if mine:
        report.errors, report.warnings = mine, []
        print_report(report)
        ok = False
    if areas & {"common", "tests", "run.py", "portfolio", "dashboard", "profiles"}:
        ok = run_tests() and ok
    return ok


# ---------------------------------------------------------------- data commands
def run_tests() -> bool:
    return subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT).returncode == 0


def cmd_check() -> int:
    from common.validate import print_report, validate_all

    report = validate_all()
    print_report(report)
    tests_ok = run_tests()
    return 0 if tests_ok and not report.errors else 1


def cmd_build(category: str, only: str | None) -> int:
    if category not in CATEGORIES:
        say(f"category must be one of {CATEGORIES}")
        return 1
    scripts = sorted(p for p in scripts_dir(category).glob("*.py") if not p.name.startswith("_"))
    if only:
        scripts = [p for p in scripts if p.stem == only]
    if not scripts:
        say(f"no scripts found in {category}/scripts/" + (f" named {only}.py" if only else ""))
        return 1
    failed = []
    for script in scripts:
        say(f"--- {category}/scripts/{script.name}")
        try:
            runpy.run_path(str(script), run_name="__main__")
        except Exception:
            traceback.print_exc()
            failed.append(script.name)
    if failed:
        say(f"FAILED: {failed}")
    return 1 if failed else 0


def cmd_new_indicator(category: str, indicator_id: str) -> int:
    from common.validate import ID_PATTERN

    if category not in CATEGORIES:
        say(f"category must be one of {CATEGORIES}")
        return 1
    if not ID_PATTERN.match(indicator_id):
        say("indicator_id must be lowercase_snake_case, e.g. ceo_pay_ratio")
        return 1
    for c in CATEGORIES:
        with catalog_path(c).open(encoding="utf-8") as f:
            if any(row["indicator_id"] == indicator_id for row in csv.DictReader(f)):
                say(f"'{indicator_id}' already exists in {c}/catalog.csv")
                return 1

    owner = git("config", "user.name").stdout.strip() or "unknown"
    path = catalog_path(category)
    text = path.read_text(encoding="utf-8")
    with path.open("a", newline="", encoding="utf-8") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        row = {c: "" for c in CATALOG_COLUMNS}
        row.update(indicator_id=indicator_id, higher_is_better="true", weight="1", owner=owner, status="idea")
        csv.DictWriter(f, fieldnames=CATALOG_COLUMNS, lineterminator="\n").writerow(row)

    script = scripts_dir(category) / f"{indicator_id}.py"
    template = (ROOT / "common" / "templates" / "indicator_script.py").read_text(encoding="utf-8")
    script.write_text(
        template.replace("{category}", category).replace("{indicator_id}", indicator_id).replace("{owner}", owner),
        encoding="utf-8",
    )
    say(f"added row to {category}/catalog.csv (status: idea, owner: {owner})")
    say(f"created {category}/scripts/{indicator_id}.py")
    say("next: fill in name/description/unit/higher_is_better/source in the catalog, then build()")
    return 0


def cmd_score(profile: str | None) -> int:
    from common.config import DEFAULT_PROFILE
    from common.score import build_scores
    from common.validate import print_report, validate_all

    report = validate_all()
    if report.errors:
        print_report(report)
        say("fix format errors before scoring")
        return 1
    try:
        build_scores(profile or DEFAULT_PROFILE)
    except (FileNotFoundError, ValueError) as e:
        say(f"STOP: {e}")
        return 1
    return 0


def cmd_dashboard() -> int:
    from dashboard.server import serve

    serve(open_browser="--no-browser" not in sys.argv)
    return 0


def cmd_setup() -> int:
    say("installing Python packages ...")
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=ROOT)
    git("config", "pull.rebase", "true")
    git("config", "rebase.autoStash", "true")
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists():
        shutil.copy(example, env)
        say("created .env from .env.example - put your email in SEC_CONTACT_EMAIL")
    name = git("config", "user.name").stdout.strip()
    email = git("config", "user.email").stdout.strip()
    if not name or not email:
        say("git does not know who you are yet. Run (with your details):")
        say('  git config --global user.name "Your Name"')
        say('  git config --global user.email "you@example.com"')
        return 1
    say(f"ready. git identity: {name} <{email}>")
    return pip.returncode


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        say(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "setup":
        return cmd_setup()
    if cmd in ("start", "sync"):
        return cmd_start()
    if cmd == "status":
        return cmd_status()
    if cmd == "save":
        if not args:
            say('usage: python run.py save "[category] what you did"')
            return 1
        return cmd_save(" ".join(args))
    if cmd == "check":
        return cmd_check()
    if cmd == "build" and args:
        return cmd_build(args[0], args[1] if len(args) > 1 else None)
    if cmd == "new-indicator" and len(args) == 2:
        return cmd_new_indicator(*args)
    if cmd == "score":
        return cmd_score(args[0] if args else None)
    if cmd == "dashboard":
        return cmd_dashboard()
    say(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
