#!/usr/bin/env python3
"""Compose the five isolated UI rewrite workstreams on the integration branch.

This script is intentionally fail-closed. It accepts only the exact audited heads
recorded in issue #18 and only the known cross-workstream conflict paths.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEADS = [
    ("foundation", "4f145d6c5ce8eb1ead0e9f2644fc3276bc2da31b"),
    ("vendor-compliance", "c94befc608bf0db458a482b39005f6b52e9746ee"),
    ("catalog-v4", "582f70b51bdee5d4e15bec124aefd17a463228d5"),
    ("performance-platform", "1a0606cc9407441766d823cbd41c4be1b1e18de4"),
    ("marketplace-interface", "d044a1ef81104a61bd6ad1abd6cf093611f6d1e5"),
]

FOUNDATION_OURS = {
    ".github/workflows/dropfinder-ci.yml",
    ".github/workflows/dropfinder-cloud.yml",
    "cloud_pages/manifest.webmanifest",
    "cloud_pages/sw.js",
}
FOUNDATION_THEIRS = {"cloud_pages/icon.svg"}
PLATFORM_OURS = {
    ".github/workflows/dropfinder-ci.yml",
    "web/package.json",
    "web/package-lock.json",
}
PLATFORM_THEIRS = {
    "cloud_pages/manifest.webmanifest",
    "cloud_pages/sw.js",
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def conflict_paths() -> set[str]:
    result = run("git", "diff", "--name-only", "--diff-filter=U")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def resolve(paths: set[str], side: str) -> None:
    for path in sorted(paths):
        run("git", "checkout", f"--{side}", "--", path)
        run("git", "add", "--", path)


def merge(label: str, sha: str) -> None:
    message = f"Merge {label} workstream at {sha[:12]}"
    result = run("git", "merge", "--no-ff", "--no-commit", sha, check=False)
    conflicts = conflict_paths()
    if result.returncode == 0:
        run("git", "commit", "-m", message)
        return

    if not conflicts:
        raise RuntimeError(f"Merge {label} failed without resolvable conflicts:\n{result.stdout}")

    if label == "foundation":
        allowed = FOUNDATION_OURS | FOUNDATION_THEIRS
        unexpected = conflicts - allowed
        if unexpected:
            raise RuntimeError(f"Unexpected foundation conflicts: {sorted(unexpected)}")
        resolve(conflicts & FOUNDATION_OURS, "ours")
        resolve(conflicts & FOUNDATION_THEIRS, "theirs")
    elif label == "performance-platform":
        allowed = PLATFORM_OURS | PLATFORM_THEIRS
        unexpected = conflicts - allowed
        if unexpected:
            raise RuntimeError(f"Unexpected platform conflicts: {sorted(unexpected)}")
        resolve(conflicts & PLATFORM_OURS, "ours")
        resolve(conflicts & PLATFORM_THEIRS, "theirs")
    else:
        raise RuntimeError(f"Unexpected conflicts while merging {label}: {sorted(conflicts)}")

    remaining = conflict_paths()
    if remaining:
        raise RuntimeError(f"Unresolved conflicts after {label}: {sorted(remaining)}")
    run("git", "commit", "-m", message)


def main() -> None:
    current = run("git", "branch", "--show-current").stdout.strip()
    if current != "ui-rewrite/06-full-integration":
        raise RuntimeError(f"Refusing to integrate on unexpected branch: {current}")
    if run("git", "status", "--porcelain").stdout.strip():
        raise RuntimeError("Integration checkout must start clean")

    run("git", "config", "user.name", "DropFinder Integration Bot")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "fetch", "--no-tags", "origin", "+refs/heads/*:refs/remotes/origin/*")

    for label, sha in HEADS:
        resolved = run("git", "rev-parse", sha).stdout.strip()
        if resolved != sha:
            raise RuntimeError(f"Could not resolve exact {label} head {sha}")
        merge(label, sha)

    run("git", "log", "--oneline", "--decorate", "-8")


if __name__ == "__main__":
    main()
