from __future__ import annotations

import http.server
import os
import socket
import threading
import unittest
from unittest.mock import patch

from scripts.vendor_adapters.fetch import fetch_public_document


class FetchSafetyTests(unittest.TestCase):
    def test_allowlisted_hostname_cannot_resolve_to_loopback(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"private-metadata"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        real_getaddrinfo = socket.getaddrinfo

        def resolve_vendor_to_loopback(host, service, *args, **kwargs):
            if host == "vendor.example":
                return real_getaddrinfo("127.0.0.1", service, *args, **kwargs)
            return real_getaddrinfo(host, service, *args, **kwargs)

        try:
            with patch.dict(
                os.environ,
                {"NO_PROXY": "vendor.example", "no_proxy": "vendor.example"},
                clear=False,
            ), patch("socket.getaddrinfo", side_effect=resolve_vendor_to_loopback):
                result = fetch_public_document(
                    f"http://vendor.example:{port}/latest/meta-data",
                    allowed_hosts={"vendor.example"},
                    timeout=2,
                    max_bytes=1024,
                )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(result.status, 0)
        self.assertEqual(result.body, b"")
        self.assertIn("non-global address 127.0.0.1", result.error)


if __name__ == "__main__":
    unittest.main()
