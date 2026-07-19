from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

repo = os.environ["GITHUB_REPOSITORY"]
token = os.environ["GITHUB_TOKEN"]
expected_sha256 = "9e9ef7df1dc6767ca4478743f326726db788bc2fcda80a695d829715ebc6a1cf"
part_pattern = re.compile(r"^bootstrap/source\.part(\d+)(?:-(\d+))?\.b64$")
count_pattern = re.compile(r"/(\d+)\b")


def api(path: str) -> object:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dropfinder-source-recovery-audit-v2",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def all_commits() -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "since": "2026-07-12T00:00:00Z",
            "until": "2026-07-16T23:59:59Z",
            "per_page": 100,
            "page": page,
        })
        batch = api(f"/repos/{repo}/commits?{query}")
        if not isinstance(batch, list):
            raise RuntimeError("commits endpoint did not return a list")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def part_range(path: str) -> tuple[int, int] | None:
    match = part_pattern.fullmatch(path)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    return start, end


def continuous(entries: list[dict], expected: int | None) -> tuple[bool, list[int]]:
    covered: set[int] = set()
    for entry in entries:
        bounds = part_range(str(entry.get("path") or ""))
        if bounds:
            covered.update(range(bounds[0], bounds[1] + 1))
    ordered = sorted(covered)
    if not ordered or ordered[0] != 0:
        return False, ordered
    inferred = expected if expected is not None else ordered[-1] + 1
    return ordered == list(range(inferred)), ordered


def raw_blob(blob_sha: str) -> bytes:
    blob = api(f"/repos/{repo}/git/blobs/{blob_sha}")
    if not isinstance(blob, dict) or "content" not in blob:
        raise RuntimeError(f"blob {blob_sha} missing content")
    return base64.b64decode(str(blob["content"]))


def attempt_snapshot(snapshot: dict) -> dict:
    entries = snapshot["entries"]
    encoded = bytearray()
    for entry in sorted(entries, key=lambda row: part_range(str(row["path"])) or (10**9, 10**9)):
        encoded.extend(raw_blob(str(entry["sha"])))
    compact = b"".join(bytes(encoded).split())
    archive = base64.b64decode(compact, validate=True)
    digest = hashlib.sha256(archive).hexdigest()
    zip_ok = False
    file_count = None
    bad_member = None
    zip_error = ""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as handle:
            bad_member = handle.testzip()
            file_count = len(handle.infolist())
            zip_ok = bad_member is None
    except Exception as exc:
        zip_error = f"{type(exc).__name__}: {exc}"
    result = {
        "sha": snapshot["sha"],
        "message": snapshot["message"],
        "committed_at": snapshot["committed_at"],
        "expected_parts": snapshot["expected_parts"],
        "covered_parts": snapshot["covered_parts"],
        "entry_paths": [entry["path"] for entry in entries],
        "decoded_bytes": len(archive),
        "sha256": digest,
        "expected_sha256": expected_sha256,
        "zip_ok": zip_ok,
        "zip_file_count": file_count,
        "zip_bad_member": bad_member,
        "zip_error": zip_error,
        "exact": digest == expected_sha256 and zip_ok,
    }
    if result["exact"]:
        result["archive"] = archive
    return result


commits = all_commits()
snapshots: list[dict] = []
errors: list[dict] = []
for row in reversed(commits):
    sha = str(row.get("sha") or "")
    message = str(((row.get("commit") or {}).get("message") or "")).splitlines()[0]
    committed_at = str((((row.get("commit") or {}).get("committer") or {}).get("date") or ""))
    if not sha:
        continue
    try:
        commit = api(f"/repos/{repo}/git/commits/{sha}")
        if not isinstance(commit, dict):
            raise RuntimeError("git commit payload is not an object")
        tree_sha = str((commit.get("tree") or {}).get("sha") or "")
        tree = api(f"/repos/{repo}/git/trees/{tree_sha}?recursive=1")
        if not isinstance(tree, dict):
            raise RuntimeError("tree payload is not an object")
        entries = [entry for entry in tree.get("tree", []) if part_range(str(entry.get("path") or ""))]
        if not entries:
            continue
        count_match = count_pattern.search(message)
        expected_parts = int(count_match.group(1)) if count_match else None
        is_continuous, covered = continuous(entries, expected_parts)
        snapshots.append({
            "sha": sha,
            "message": message,
            "committed_at": committed_at,
            "expected_parts": expected_parts,
            "covered_parts": covered,
            "continuous": is_continuous,
            "entries": entries,
        })
    except Exception as exc:
        errors.append({"sha": sha, "message": message, "error": f"{type(exc).__name__}: {exc}"})

candidates = sorted(
    [snapshot for snapshot in snapshots if snapshot["continuous"]],
    key=lambda snapshot: (
        len(snapshot["covered_parts"]),
        snapshot["expected_parts"] or 0,
        snapshot["committed_at"],
    ),
    reverse=True,
)
attempts: list[dict] = []
recovered: bytes | None = None
for snapshot in candidates:
    try:
        result = attempt_snapshot(snapshot)
    except Exception as exc:
        result = {
            "sha": snapshot["sha"],
            "message": snapshot["message"],
            "committed_at": snapshot["committed_at"],
            "expected_parts": snapshot["expected_parts"],
            "covered_parts": snapshot["covered_parts"],
            "entry_paths": [entry["path"] for entry in snapshot["entries"]],
            "error": f"{type(exc).__name__}: {exc}",
            "exact": False,
        }
    archive = result.pop("archive", None)
    attempts.append(result)
    if archive is not None:
        recovered = archive
        break

report = {
    "repository": repo,
    "commits_inspected": len(commits),
    "snapshots_with_parts": len(snapshots),
    "continuous_candidates": len(candidates),
    "max_covered_parts": max((len(snapshot["covered_parts"]) for snapshot in snapshots), default=0),
    "max_snapshot": max(
        (
            {
                "sha": snapshot["sha"],
                "message": snapshot["message"],
                "committed_at": snapshot["committed_at"],
                "expected_parts": snapshot["expected_parts"],
                "covered_parts": snapshot["covered_parts"],
                "entry_paths": [entry["path"] for entry in snapshot["entries"]],
                "continuous": snapshot["continuous"],
            }
            for snapshot in snapshots
        ),
        key=lambda snapshot: len(snapshot["covered_parts"]),
        default=None,
    ),
    "attempts": attempts,
    "errors": errors,
    "expected_sha256": expected_sha256,
    "recovered": recovered is not None,
}
Path("/tmp/issue4-archive-history.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
lines = [
    "# Issue 4 archive-history recovery v2",
    "",
    f"- Commits inspected: {report['commits_inspected']}",
    f"- Snapshots containing parts: {report['snapshots_with_parts']}",
    f"- Continuous candidates: {report['continuous_candidates']}",
    f"- Maximum covered part count: {report['max_covered_parts']}",
    f"- Exact archive recovered: {report['recovered']}",
    "",
    "## Strongest attempts",
]
for attempt in attempts[:20]:
    lines.append(
        f"- `{attempt['sha']}` covered={len(attempt.get('covered_parts', []))} "
        f"expected={attempt.get('expected_parts')} bytes={attempt.get('decoded_bytes', 'n/a')} "
        f"sha256={attempt.get('sha256', 'n/a')} zip_ok={attempt.get('zip_ok', False)} "
        f"exact={attempt.get('exact', False)} error={attempt.get('error') or attempt.get('zip_error') or 'none'}"
    )
Path("/tmp/issue4-archive-history.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
if recovered is not None:
    Path("/tmp/dropfinder-os-v9-recovered.zip").write_bytes(recovered)
print(Path("/tmp/issue4-archive-history.md").read_text(encoding="utf-8"))
