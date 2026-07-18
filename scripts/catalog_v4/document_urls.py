from __future__ import annotations

import re
import urllib.parse
from typing import Any

from .normalization import clean_text

TRACKING_QUERY_KEYS = {
    "_hsenc",
    "_hsmi",
    "dclid",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
}
EPHEMERAL_QUERY_KEYS = {
    "access_token",
    "auth",
    "authorization",
    "awsaccesskeyid",
    "expires",
    "expiration",
    "expiry",
    "key-pair-id",
    "policy",
    "sig",
    "signature",
    "token",
}
EPHEMERAL_QUERY_PREFIXES = ("x-amz-", "x-goog-", "x-oss-")


def canonical_document_url(value: Any) -> str:
    """Return a stable public document URL without erasing resource identity.

    Document endpoints commonly use ordinary query parameters as part of the
    resource identity. Preserve those parameters, remove only known analytics
    keys, and reject credentialed or expiring signed URLs that cannot remain a
    durable public catalog reference.
    """

    raw = clean_text(value)
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username is not None or parsed.password is not None:
        return ""

    try:
        raw_query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return ""
    folded_keys = {key.casefold() for key, _ in raw_query}
    if any(
        key in EPHEMERAL_QUERY_KEYS or key.startswith(EPHEMERAL_QUERY_PREFIXES)
        for key in folded_keys
    ):
        return ""
    if "sig" in folded_keys or ({"se", "sv"} <= folded_keys):
        return ""

    query = [
        (key, val)
        for key, val in raw_query
        if key.casefold() not in TRACKING_QUERY_KEYS
        and not key.casefold().startswith("utm_")
    ]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urllib.parse.urlencode(sorted(query)),
            "",
        )
    )
