from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

repo = os.environ["GITHUB_REPOSITORY"]
token = os.environ["GITHUB_TOKEN"]
expected_sha256 = "9e9ef7df1dc6767ca4478743f326726db788bc2fcda80a695d829715ebc6a1cf"


def api(path: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "dropfinder-source-recovery-audit",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


query = urllib.parse.quote(f"repo:{repo} committer-date:2026-07-13..2026-07-14")
search = api(f"/search/commits?q={query}&per_page=100")
items = search.get("items", [])
records = []
candidates = []
for item in items:
    sha = str(item.get("sha") or "")
    if not sha:
        continue
    try:
        commit = api(f"/repos/{repo}/git/commits/{sha}")
        tree_sha = commit["tree"]["sha"]
        tree = api(f"/repos/{repo}/git/trees/{tree_sha}?recursive=1")
    except Exception as exc:
        records.append({"sha": sha, "error": f"{type(exc).__name__}: {exc}"})
        continue
    entries = tree.get("tree", [])
    part_entries = sorted(
        [entry for entry in entries if str(entry.get("path") or "").startswith("bootstrap/source.part") and str(entry.get("path") or "").endswith(".b64")],
        key=lambda entry: str(entry["path"]),
    )
    checksum_entries = [entry for entry in entries if str(entry.get("path") or "") == "bootstrap/source.sha256"]
    archive_entries = [entry for entry in entries if str(entry.get("path") or "").endswith((".zip", ".bundle"))]
    if part_entries or checksum_entries or archive_entries:
        message = str((item.get("commit") or {}).get("message") or "").splitlines()[0]
        record = {
            "sha": sha,
            "message": message,
            "part_count": len(part_entries),
            "parts": [entry["path"] for entry in part_entries],
            "checksum_present": bool(checksum_entries),
            "archive_paths": [entry["path"] for entry in archive_entries],
        }
        records.append(record)
        if part_entries:
            candidates.append((len(part_entries), sha, part_entries, checksum_entries, message))

attempts = []
recovered = None
for part_count, sha, part_entries, checksum_entries, message in sorted(candidates, reverse=True):
    try:
        encoded = bytearray()
        for entry in part_entries:
            blob = api(f"/repos/{repo}/git/blobs/{entry['sha']}")
            encoded.extend(base64.b64decode(blob["content"]))
        archive = base64.b64decode(b"".join(encoded.split()), validate=True)
        digest = hashlib.sha256(archive).hexdigest()
        checksum_text = ""
        if checksum_entries:
            blob = api(f"/repos/{repo}/git/blobs/{checksum_entries[0]['sha']}")
            checksum_text = base64.b64decode(blob["content"]).decode("utf-8", "replace").strip()
        zip_ok = False
        file_count = None
        zip_error = ""
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as handle:
                bad = handle.testzip()
                zip_ok = bad is None
                file_count = len(handle.infolist())
                if bad:
                    zip_error = f"bad member: {bad}"
        except Exception as exc:
            zip_error = f"{type(exc).__name__}: {exc}"
        attempt = {
            "sha": sha,
            "message": message,
            "part_count": part_count,
            "decoded_bytes": len(archive),
            "sha256": digest,
            "expected_sha256": expected_sha256,
            "checksum_text": checksum_text,
            "zip_ok": zip_ok,
            "zip_file_count": file_count,
            "zip_error": zip_error,
        }
        attempts.append(attempt)
        if digest == expected_sha256 and zip_ok:
            recovered = archive
            break
    except Exception as exc:
        attempts.append({
            "sha": sha,
            "message": message,
            "part_count": part_count,
            "error": f"{type(exc).__name__}: {exc}",
        })

report = {
    "repository": repo,
    "searched_commits": len(items),
    "archive_related_commits": records,
    "candidate_attempts": attempts,
    "expected_sha256": expected_sha256,
    "recovered": recovered is not None,
}
Path("/tmp/issue4-archive-history.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
lines = [
    "# Issue 4 archive-history recovery",
    "",
    f"- Search results inspected: {len(items)}",
    f"- Archive-related commits: {len(records)}",
    f"- Candidate trees attempted: {len(attempts)}",
    f"- Exact archive recovered: {recovered is not None}",
    "",
    "## Candidate attempts",
]
for attempt in attempts:
    lines.append(
        f"- `{attempt['sha']}` parts={attempt['part_count']} "
        f"bytes={attempt.get('decoded_bytes', 'n/a')} sha256={attempt.get('sha256', 'n/a')} "
        f"zip_ok={attempt.get('zip_ok', False)} error={attempt.get('error') or attempt.get('zip_error') or 'none'}"
    )
Path("/tmp/issue4-archive-history.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
if recovered is not None:
    Path("/tmp/dropfinder-os-v9-recovered.zip").write_bytes(recovered)
print(Path("/tmp/issue4-archive-history.md").read_text(encoding="utf-8"))
