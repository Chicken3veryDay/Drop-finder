from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any


REPO = os.environ["GITHUB_REPOSITORY"]
DEFAULT = os.environ.get("DEFAULT_BRANCH", "main")
SELF_BASE = os.environ.get("SELF_BASE", "cleanup/final-repository")
SELF_TRIGGER = os.environ.get("SELF_TRIGGER", "trigger/final-repository-cleanup")
REPORT = Path(os.environ.get("REPORT", "/tmp/final-branch-cleanup.json"))


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def gh(endpoint: str, method: str = "GET") -> Any:
    result = run("gh", "api", "--method", method, endpoint)
    return json.loads(result.stdout) if result.stdout.strip() else None


def paged(endpoint: str) -> list[Any]:
    separator = "&" if "?" in endpoint else "?"
    pages = json.loads(run("gh", "api", "--paginate", "--slurp", f"{endpoint}{separator}per_page=100").stdout)
    flattened: list[Any] = []
    for page in pages:
        if isinstance(page, list):
            flattened.extend(page)
        elif isinstance(page, dict):
            for key in ("workflow_runs", "deployments", "releases", "tags", "branches"):
                if isinstance(page.get(key), list):
                    flattened.extend(page[key])
                    break
    return flattened


def ancestor(branch: str, target: str) -> bool:
    return run("git", "merge-base", "--is-ancestor", f"origin/{branch}", f"origin/{target}", check=False).returncode == 0


def changed_paths(branch: str) -> list[str]:
    merge_base = run("git", "merge-base", f"origin/{DEFAULT}", f"origin/{branch}").stdout.strip()
    output = run("git", "diff", "--name-only", merge_base, f"origin/{branch}").stdout
    return sorted({line.strip() for line in output.splitlines() if line.strip()})


def path_bytes(ref: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"origin/{ref}:{path}"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout if result.returncode == 0 else None


def temporary_path(path: str) -> bool:
    return (
        path.startswith(".github/tmp/")
        or path.startswith(".github/workflows/tmp-")
        or path.endswith("/trigger.txt")
        or path.endswith("-trigger.txt")
        or path.startswith("verification/final-production/")
        or path == "web/playwright.live.config.mjs"
        or path == "web/tests/e2e/live-production.spec.mjs"
    )


def duplicate_or_temporary(branch: str, paths: list[str]) -> tuple[bool, list[str]]:
    unresolved: list[str] = []
    for path in paths:
        if temporary_path(path):
            continue
        if path_bytes(branch, path) == path_bytes(DEFAULT, path):
            continue
        unresolved.append(path)
    return not unresolved, unresolved


def encoded_ref(branch: str) -> str:
    return urllib.parse.quote(f"heads/{branch}", safe="")


def main() -> int:
    run("git", "fetch", "--all", "--prune", "+refs/heads/*:refs/remotes/origin/*")
    repository = gh(f"repos/{REPO}")
    branches = paged(f"repos/{REPO}/branches")
    pulls = paged(f"repos/{REPO}/pulls?state=open")
    runs = paged(f"repos/{REPO}/actions/runs?status=queued") + paged(f"repos/{REPO}/actions/runs?status=in_progress")
    deployments = paged(f"repos/{REPO}/deployments")
    releases = paged(f"repos/{REPO}/releases")
    tags = paged(f"repos/{REPO}/tags")
    environments = gh(f"repos/{REPO}/environments") or {}

    open_heads = {str(item.get("head", {}).get("ref")) for item in pulls}
    active_heads = {str(item.get("head_branch")) for item in runs if item.get("head_branch")}
    deployment_refs = {str(item.get("ref")) for item in deployments if item.get("ref")}
    release_targets = {str(item.get("target_commitish")) for item in releases if item.get("target_commitish")}
    protected = {str(item.get("name")) for item in branches if item.get("protected")}
    tag_commits = {str(item.get("commit", {}).get("sha")) for item in tags if item.get("commit")}

    records: list[dict[str, Any]] = []
    planned: list[str] = []
    blockers: list[str] = []
    for item in sorted(branches, key=lambda value: str(value.get("name"))):
        branch = str(item["name"])
        tip = str(item["commit"]["sha"])
        record: dict[str, Any] = {
            "branch": branch,
            "tip": tip,
            "protected": branch in protected,
            "open_pr": branch in open_heads,
            "active_workflow": branch in active_heads,
            "deployment_ref": branch in deployment_refs,
            "release_target": branch in release_targets,
            "tagged_tip": tip in tag_commits,
            "reachable_from_main": ancestor(branch, DEFAULT),
            "reachable_from_gh_pages": branch == "gh-pages" or ancestor(branch, "gh-pages"),
        }
        reasons: list[str] = []
        if branch in {DEFAULT, "gh-pages", SELF_BASE, SELF_TRIGGER}:
            reasons.append("required branch")
        if record["protected"]:
            reasons.append("protected")
        if record["open_pr"]:
            reasons.append("open pull request")
        if record["active_workflow"]:
            reasons.append("active workflow")
        if record["deployment_ref"]:
            reasons.append("deployment reference")
        if record["release_target"]:
            reasons.append("release target")
        if record["tagged_tip"]:
            reasons.append("tagged tip")

        if reasons:
            record.update({"decision": "retain", "reasons": reasons})
        elif record["reachable_from_main"] or record["reachable_from_gh_pages"]:
            record.update({"decision": "delete", "proof": "tip reachable from retained branch"})
            planned.append(branch)
        else:
            paths = changed_paths(branch)
            safe, unresolved = duplicate_or_temporary(branch, paths)
            record["changed_paths"] = paths
            record["unresolved_unique_paths"] = unresolved
            if safe:
                record.update({"decision": "delete", "proof": "unique diff is temporary or byte-identical to main"})
                planned.append(branch)
            else:
                record.update({"decision": "retain", "reasons": ["unresolved unique commits"]})
                blockers.append(branch)
        records.append(record)

    deletions: list[dict[str, Any]] = []
    for branch in planned:
        result = run("gh", "api", "--method", "DELETE", f"repos/{REPO}/git/refs/{encoded_ref(branch)}", check=False)
        deletions.append({
            "branch": branch,
            "status": "deleted" if result.returncode == 0 else "failed",
            "stderr": result.stderr.strip(),
        })
        if result.returncode != 0:
            blockers.append(branch)

    report = {
        "repository": REPO,
        "default_branch": repository.get("default_branch"),
        "main_sha": run("git", "rev-parse", f"origin/{DEFAULT}").stdout.strip(),
        "gh_pages_sha": run("git", "rev-parse", "origin/gh-pages").stdout.strip(),
        "open_pull_requests": sorted(open_heads),
        "active_workflow_branches": sorted(active_heads),
        "deployment_refs": sorted(deployment_refs),
        "release_targets": sorted(release_targets),
        "protected_branches": sorted(protected),
        "environments": environments.get("environments", []),
        "tags": tags,
        "branches": records,
        "deletions": deletions,
        "unresolved_branches": sorted(set(blockers)),
        "complete": not blockers,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"complete": report["complete"], "deleted": sum(item["status"] == "deleted" for item in deletions), "unresolved": report["unresolved_branches"]}, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
