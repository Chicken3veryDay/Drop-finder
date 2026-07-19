# Document image validation

Document previews are not considered ready merely because a URL was classified as an image or returned an image-like content type.

The document viewer applies one decode boundary to both fetched image bytes and direct image URLs:

1. fetched bytes are bounded by the document size limit;
2. fetched bytes are wrapped in a temporary object URL;
3. the browser image decoder must complete successfully;
4. readiness is published only while the same document session still owns the request;
5. temporary object URLs are revoked on decode failure, abort, supersession, and close.

HTML challenge pages, corrupt bytes, and unsupported decoders fail with an `image_decode_failed` or `image_decode_unavailable` error while preserving the original link for external opening. A successful fetched preview retains its object URL only for the active viewer session.

Lifecycle tests that are intended to exercise cleanup ordering rather than decoding must provide an explicit successful decoder. This keeps the cleanup contract independent without bypassing the production decode boundary.
