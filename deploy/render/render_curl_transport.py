from __future__ import annotations

import json
import subprocess
from typing import Any


def apply(render_deploy) -> None:
    """Replace urllib Render API calls with a bounded curl transport."""

    def curl_request(self, method: str, path: str, payload: Any | None = None) -> Any:
        method_upper = method.upper()
        retries = 5 if method_upper in {"GET", "PUT", "PATCH", "DELETE"} else 0
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--http1.1",
            "--connect-timeout",
            "20",
            "--max-time",
            "180",
            "--retry",
            str(retries),
            "--retry-all-errors",
            "--retry-delay",
            "3",
            "--request",
            method_upper,
            "--header",
            "Accept: application/json",
            "--header",
            f"Authorization: Bearer {self.token}",
            "--header",
            "Content-Type: application/json",
            "--header",
            "User-Agent: DropFinder-Render-Deployer-Curl/1.0",
            "--write-out",
            "\n%{http_code}",
            render_deploy.API_ROOT + path,
        ]
        body = None
        if payload is not None:
            command.extend(["--data-binary", "@-"])
            body = json.dumps(payload).encode("utf-8")
        process = subprocess.run(
            command,
            input=body,
            capture_output=True,
            timeout=240,
            check=False,
        )
        stdout = process.stdout.decode("utf-8", "replace")
        stderr = process.stderr.decode("utf-8", "replace")
        if process.returncode != 0:
            raise TimeoutError(
                f"Render API curl {method_upper} {path} failed with exit {process.returncode}: "
                f"{stderr[-2000:] or stdout[-2000:]}"
            )
        try:
            raw, status_text = stdout.rsplit("\n", 1)
            status = int(status_text.strip())
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"Render API curl {method_upper} {path} returned an unreadable response: "
                f"{stdout[-2000:]} {stderr[-1000:]}"
            ) from exc
        if not 200 <= status < 300:
            raise RuntimeError(
                f"Render API {method_upper} {path} returned HTTP {status}: {raw[:4000]}"
            )
        raw = raw.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Render API {method_upper} {path} returned invalid JSON: {raw[:4000]}"
            ) from exc

    render_deploy.RenderAPI.request = curl_request
