#!/usr/bin/env python3
"""Fail the build if organization-specific vocabulary reaches the repository.

Warrant is a public project. Access-control code is unusually prone to leaking
the structure of whatever organization it was first built for -- internal
seniority ladders, team identifiers, hostnames, ticket IDs. Once any of that
lands in git history it is effectively permanent: history rewrites are
disruptive, forks are already cloned, and code search has indexed it.

So this is a mandate, not a guideline, and it is enforced here rather than in
a style doc that nobody re-reads.

Two layers
----------
1. **Structural patterns (committed, below).** These match the *shape* of
   internal vocabulary without naming any real organization, so the checker
   itself leaks nothing.

2. **A local denylist (never committed).** ``.vocabulary-denylist`` is
   gitignored. Put literal terms there that must not escape -- internal system
   names, team names, codenames. Because the file stays on your machine and in
   your CI secrets, the list of things you are protecting is not itself
   published. This is the part people get backwards: shipping a denylist of
   internal codenames publishes the codenames.

Escape hatch
------------
Append ``# vocab-ok: <reason>`` to a line to suppress it. Suppressions are
greppable, so they can be audited.

Usage
-----
    python scripts/check_vocabulary.py            # scan tracked files
    python scripts/check_vocabulary.py path ...   # scan specific paths
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Iterable, List, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENYLIST_FILE = os.path.join(REPO_ROOT, ".vocabulary-denylist")
SUPPRESSION = re.compile(r"#\s*vocab-ok\b")

# Files that may legitimately discuss the rules themselves.
EXEMPT_PATHS = {
    "scripts/check_vocabulary.py",
    "docs/decisions/0001-no-organization-specific-vocabulary.md",
    "CONTRIBUTING.md",
}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".ico",
    ".woff", ".woff2", ".ttf", ".so", ".dylib", ".whl",
}

# Domains that are reserved by RFC 2606 / RFC 6761 for documentation and
# testing. Anything else that looks like a corporate domain is suspect.
SAFE_DOMAIN = re.compile(r"\b(?:example\.(?:com|org|net)|example\.test|localhost)\b")

Pattern = Tuple[str, "re.Pattern[str]", str]

STRUCTURAL_PATTERNS: Sequence[Pattern] = (
    (
        "employee-level-ladder",
        # Matches L4..L19-style seniority markers. L1/L2/L3 are deliberately
        # excluded: in a retrieval codebase they overwhelmingly mean cache
        # levels or L2 distance, not job levels.
        re.compile(r"\bL(?:[4-9]|1\d)\b"),
        "Looks like an internal seniority ladder. Use an integer `clearance` "
        "tier supplied by configuration instead.",
    ),
    (
        "org-prefixed-identifier",
        re.compile(r"\borg-[a-z][a-z0-9-]{2,}", re.IGNORECASE),
        "Looks like a real org identifier. Use a neutral example group such "
        "as `finance` or `engineering`.",
    ),
    (
        "internal-hostname",
        re.compile(r"\b[\w-]+\.(?:corp|internal|intranet|lan)\b", re.IGNORECASE),
        "Internal hostname. Use example.com or a configuration value.",
    ),
    (
        "internal-ticket-id",
        re.compile(r"\b(?:TT|SIM|JIRA|INC)[-/][A-Z0-9]{4,}\b"),
        "Internal ticket reference. Describe the problem instead of linking "
        "to a tracker nobody outside can open.",
    ),
    (
        "non-example-corporate-email",
        re.compile(r"\b[\w.+-]+@(?!example\.(?:com|org|net|test)\b)[\w-]+\.[a-z]{2,}\b"),
        "Email address on a non-example domain. Use user@example.test.",
    ),
)


def load_denylist() -> List[str]:
    if not os.path.exists(DENYLIST_FILE):
        return []
    terms = []
    with open(DENYLIST_FILE, "r", encoding="utf-8") as fh:
        for raw in fh:
            term = raw.strip()
            if term and not term.startswith("#"):
                terms.append(term)
    return terms


def tracked_files() -> List[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not a git repo yet (e.g. first run before `git init`) -- walk instead.
        collected = []
        for root, dirs, files in os.walk(REPO_ROOT):
            dirs[:] = [d for d in dirs if d not in {".git", ".venv", "__pycache__", "node_modules"}]
            for name in files:
                collected.append(
                    os.path.relpath(os.path.join(root, name), REPO_ROOT)
                )
        return collected
    return [line for line in out.splitlines() if line]


def scan_line(line: str, denylist: Sequence[str]) -> List[Tuple[str, str, str]]:
    """Return (rule, matched_text, guidance) for each violation on the line."""
    if SUPPRESSION.search(line):
        return []

    findings = []
    for rule, pattern, guidance in STRUCTURAL_PATTERNS:
        for match in pattern.finditer(line):
            text = match.group(0)
            if rule == "non-example-corporate-email" and SAFE_DOMAIN.search(text):
                continue
            findings.append((rule, text, guidance))

    lowered = line.lower()
    for term in denylist:
        if term.lower() in lowered:
            findings.append(
                (
                    "local-denylist",
                    "<redacted>",  # never echo the secret term into CI logs
                    "Matched an entry in your local .vocabulary-denylist.",
                )
            )
    return findings


def check(paths: Iterable[str], denylist: Sequence[str]) -> int:
    violations = 0
    for rel in paths:
        if rel in EXEMPT_PATHS:
            continue
        if os.path.splitext(rel)[1].lower() in BINARY_SUFFIXES:
            continue
        full = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except (UnicodeDecodeError, OSError):
            continue

        for number, line in enumerate(lines, start=1):
            for rule, text, guidance in scan_line(line, denylist):
                violations += 1
                print(f"{rel}:{number}: [{rule}] {text}")
                print(f"    {guidance}")

    return violations


def main(argv: Sequence[str]) -> int:
    denylist = load_denylist()
    paths = list(argv[1:]) or tracked_files()
    violations = check(paths, denylist)

    if violations:
        print(
            f"\n{violations} vocabulary violation(s). This is a public "
            f"repository and git history is effectively permanent.\n"
            f"Fix the wording, or append `# vocab-ok: <reason>` to the line "
            f"if it is a genuine false positive.",
            file=sys.stderr,
        )
        return 1

    if not denylist:
        print(
            "note: no .vocabulary-denylist found. Structural patterns ran, but "
            "literal internal terms are unchecked. See CONTRIBUTING.md."
        )
    print("✓ vocabulary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
