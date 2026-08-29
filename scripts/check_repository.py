#!/usr/bin/env python3
"""Repository hygiene checks: licensing, attribution, and nothing leaked.

Two classes of problem this catches:

* Attribution quietly disappearing. The Open Parliament Licence notice and the
  unofficial disclaimer are obligations, not decoration, and they are easy to
  delete by accident while refactoring a footer.
* Secrets or Terraform state being committed. Both are far cheaper to prevent
  than to remediate.

Usage::

    python scripts/check_repository.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

OPL_SENTENCE = (
    "Contains Parliamentary information licensed under the Open Parliament Licence v3.0."
)
OPL_URL = (
    "https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/"
)
DISCLAIMER = (
    "This is an independent, unofficial project and is not affiliated with or endorsed by "
    "UK Parliament."
)

#: File name patterns that must never be committed.
FORBIDDEN_NAMES = [
    (re.compile(r"\.tfstate(\.backup)?$"), "Terraform state"),
    (re.compile(r"^terraform\.tfvars$"), "Terraform variables hold deployment specifics"),
    (re.compile(r"^backend\.hcl$"), "backend configuration names a real bucket"),
    (re.compile(r"^\.env$"), "environment file"),
    (re.compile(r"^credentials$"), "AWS credentials file"),
    (re.compile(r"\.pem$"), "private key"),
    (re.compile(r"\.p12$"), "key store"),
    (re.compile(r"^id_rsa$"), "private key"),
]

#: Content patterns that look like a leaked credential.
SECRET_PATTERNS = [
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"aws_secret_access_key\s*=\s*[\"']?[A-Za-z0-9/+=]{40}"), "AWS secret key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "GitHub personal access token"),
]

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".tf",
    ".hcl",
    ".md",
    ".yml",
    ".yaml",
    ".css",
    ".html",
    ".sh",
    ".txt",
    ".toml",
    ".cfg",
}

#: A markdown link, so it can be reduced to the text a reader actually sees.
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


@dataclass
class Finding:
    where: str
    detail: str


def committed_files() -> list[Path]:
    """Every file that would end up in a commit.

    ``--cached`` picks up what is already tracked and ``--others`` adds new
    files, while ``--exclude-standard`` applies .gitignore. That combination is
    what makes this correct before the first commit as well as after it: an
    ignored local terraform.tfvars is not committed, and must not be reported
    as though it were.
    """
    try:
        output = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return [REPO_ROOT / line for line in output.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        # No git available. Fall back to a walk, accepting that it cannot
        # honour .gitignore.
        skip = {".git", "node_modules", ".venv", "dist", "build", ".terraform", "coverage"}
        return [
            path
            for path in REPO_ROOT.rglob("*")
            if path.is_file() and not any(part in skip for part in path.parts)
        ]


def prose(text: str) -> str:
    """Flatten prose so a wrapped sentence still matches.

    The attribution is a sentence, not a line. It is quite reasonably wrapped
    across lines, placed inside a blockquote, and has the licence name as a
    link. Matching the raw text would fail on all three, so links are reduced
    to their visible text and whitespace is collapsed.
    """
    flattened = MARKDOWN_LINK.sub(lambda match: match.group(1), text)
    flattened = flattened.replace("> ", " ").replace("&rsquo;", "'")
    return " ".join(flattened.split())


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def check_licence_files() -> list[Finding]:
    findings: list[Finding] = []
    licence = REPO_ROOT / "LICENSE"
    notices = REPO_ROOT / "THIRD_PARTY_NOTICES.md"

    if not licence.is_file():
        findings.append(Finding("LICENSE", "is missing"))
    elif "MIT License" not in read(licence):
        findings.append(Finding("LICENSE", "does not look like the MIT licence"))

    if not notices.is_file():
        findings.append(Finding("THIRD_PARTY_NOTICES.md", "is missing"))
        return findings

    raw = read(notices)
    flat = prose(raw)

    if OPL_SENTENCE not in flat:
        findings.append(
            Finding("THIRD_PARTY_NOTICES.md", "is missing the Open Parliament Licence attribution")
        )
    # Checked against the raw text, because prose() strips URLs out of links.
    if OPL_URL not in raw:
        findings.append(Finding("THIRD_PARTY_NOTICES.md", "does not link to the licence"))

    # The MIT grant must be explicitly bounded, or it reads as though it
    # relicensed Parliamentary information.
    if "not to Parliamentary information" not in flat and "excluded from the MIT grant" not in flat:
        findings.append(
            Finding(
                "THIRD_PARTY_NOTICES.md",
                "does not state that the MIT licence excludes Parliamentary information",
            )
        )
    return findings


def check_readme_attribution() -> list[Finding]:
    readme = REPO_ROOT / "README.md"
    if not readme.is_file():
        return [Finding("README.md", "is missing")]

    raw = read(readme)
    flat = prose(raw)
    findings = []
    for needle, why in [
        (OPL_SENTENCE, "the Open Parliament Licence attribution"),
        ("Unofficial project", "the unofficial notice"),
        ("TLDR News", "the inspiration acknowledgement"),
    ]:
        if needle not in flat:
            findings.append(Finding("README.md", f"is missing {why}"))
    if OPL_URL not in raw:
        findings.append(Finding("README.md", "does not link to the licence"))
    return findings


def check_ui_attribution() -> list[Finding]:
    """The deployed page must carry both notices, not just the repository."""
    footer = REPO_ROOT / "frontend" / "src" / "components" / "AttributionFooter.tsx"
    if not footer.is_file():
        return [Finding("AttributionFooter.tsx", "is missing")]

    raw = read(footer)
    flat = prose(raw)
    findings = []
    if "Contains Parliamentary information licensed under the" not in flat:
        findings.append(Finding("AttributionFooter.tsx", "is missing the licence sentence"))
    if "Open Parliament Licence v3.0" not in flat:
        findings.append(Finding("AttributionFooter.tsx", "does not name the licence"))
    if OPL_URL not in raw:
        findings.append(Finding("AttributionFooter.tsx", "does not link to the licence"))
    if " ".join(DISCLAIMER.split()) not in flat:
        findings.append(Finding("AttributionFooter.tsx", "is missing the unofficial disclaimer"))
    return findings


def check_no_forbidden_files(files: list[Path]) -> list[Finding]:
    findings = []
    for path in files:
        for pattern, why in FORBIDDEN_NAMES:
            if pattern.search(path.name):
                findings.append(
                    Finding(str(path.relative_to(REPO_ROOT)), f"must not be committed ({why})")
                )
    return findings


def check_no_secrets(files: list[Path]) -> list[Finding]:
    findings = []
    for path in files:
        if path.suffix not in TEXT_SUFFIXES:
            continue
        # This file necessarily contains the patterns it searches for.
        if path.name == Path(__file__).name:
            continue
        text = read(path)
        for pattern, why in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    Finding(str(path.relative_to(REPO_ROOT)), f"looks like it contains a {why}")
                )
    return findings


def main() -> int:
    files = committed_files()

    checks = {
        "licence files": check_licence_files,
        "README attribution": check_readme_attribution,
        "in-application attribution": check_ui_attribution,
        "no state or credential files committed": lambda: check_no_forbidden_files(files),
        "no secrets in committed files": lambda: check_no_secrets(files),
    }

    total = 0
    for name, check in checks.items():
        findings = check()
        total += len(findings)
        if findings:
            print(f"FAIL  {name}")
            for finding in findings:
                print(f"        {finding.where} {finding.detail}")
        else:
            print(f"ok    {name}")

    if total:
        print(f"\n{total} repository issue(s).", file=sys.stderr)
        return 1

    print(f"\nChecked {len(files)} files. No issues.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
