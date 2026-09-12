# Environment check. Run this FIRST if anything is broken.
#   python run.py doctor
# OWNER: Arash.

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, WARN, BAD = "[ ok ]", "[warn]", "[FAIL]"
problems = 0


def check(label: str, good: bool, fix: str = "", *, fatal: bool = True) -> None:
    global problems
    if good:
        print(f"{OK} {label}")
        return
    print(f"{BAD if fatal else WARN} {label}")
    if fix:
        print(f"       fix: {fix}")
    if fatal:
        problems += 1


print("=== python ===")
check(f"python {sys.version.split()[0]}", sys.version_info >= (3, 11),
      "install Python 3.11 or newer")

print("\n=== packages ===")
for pkg, why in [
    ("pandas", "core"), ("numpy", "core"), ("pyarrow", "parquet"),
    ("requests", "data fetching"), ("streamlit", "dashboard"),
    ("plotly", "charts"), ("sklearn", "embeddings + reranker"),
    ("pytest", "tests"), ("dotenv", ".env loading"),
]:
    check(f"{pkg} ({why})", importlib.util.find_spec(pkg) is not None,
          "pip install -r requirements.txt")

print("\n=== optional packages ===")
for pkg, why in [("anthropic", "extraction + red-team agents"),
                 ("lightgbm", "reranker / abatement model")]:
    check(f"{pkg} ({why})", importlib.util.find_spec(pkg) is not None,
          "pip install -r requirements.txt", fatal=False)

print("\n=== .env ===")
envfile = ROOT / ".env"
check(".env exists", envfile.exists(),
      "copy .env.example to .env  (Windows: copy .env.example .env)", fatal=False)
if envfile.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(envfile)
    except ImportError:
        pass
has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
check("ANTHROPIC_API_KEY set", has_key,
      "only Jean (extraction) and Harprit (red-team) need this - ignore otherwise",
      fatal=False)
check("SEC_CONTACT_EMAIL set", bool(os.environ.get("SEC_CONTACT_EMAIL")),
      "SEC blocks requests without a contact email in the User-Agent", fatal=False)

print("\n=== data ===")
mock = ROOT / "data" / "mock" / "company_scores.parquet"
check("mock data generated", mock.exists(), "python run.py mocks", fatal=False)

print("\n=== git ===")
check("git repo", (ROOT / ".git").exists(), "")
check("origin configured",
      "origin" in os.popen("git -C %s remote" % ROOT).read(), "")

print()
if problems:
    print(f"{problems} blocking problem(s). Fix those first.")
    sys.exit(1)
print("Environment is good. Next:  python run.py mocks && python run.py test")
