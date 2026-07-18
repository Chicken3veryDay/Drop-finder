from __future__ import annotations

import http.server
import os
import socket
import ssl
import threading
import unittest
from unittest.mock import patch

from scripts.vendor_adapters.fetch import _PinnedHTTPSConnection, fetch_public_document


def _answer(address: str, port: int):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


class _FakeResponse:
    def __init__(self, status=200, headers=None, body=b"ok"):
        self.status = status
        self._headers = dict(headers or {})
        self._body = body
        self.closed = False

    def getheader(self, name, default=None):
        for key, value in self._headers.items():
            if key.lower() == name.lower():
                return value
        return default

    def read(self, amount=-1):
        return self._body if amount < 0 else self._body[:amount]

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls
        self.closed = False

    def request(self, method, target, body=None, headers=None):
        self.calls.append((method, target, dict(headers or {})))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class FetchSafetyTests(unittest.TestCase):
    def test_default_transport_rejects_dns_to_loopback_before_request(self):
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

        def resolver(host, service, *args, **kwargs):
            if host == "vendor.example":
                return real_getaddrinfo("127.0.0.1", service, *args, **kwargs)
            return real_getaddrinfo(host, service, *args, **kwargs)

        try:
            with patch.dict(
                os.environ,
                {"NO_PROXY": "vendor.example", "no_proxy": "vendor.example"},
                clear=False,
            ), patch("socket.getaddrinfo", side_effect=resolver):
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

    def test_mixed_public_and_private_answers_fail_closed(self):
        connector_calls = []

        def resolver(host, port, **kwargs):
            return [_answer("93.184.216.34", port), _answer("10.0.0.7", port)]

        def connector(*args):
            connector_calls.append(args)
            raise AssertionError("connector must not run")

        result = fetch_public_document(
            "https://vendor.example/report",
            allowed_hosts={"vendor.example"},
            _resolver=resolver,
            _connection_factory=connector,
        )
        self.assertIn("non-global address 10.0.0.7", result.error)
        self.assertEqual(connector_calls, [])

    def test_pins_validated_address_and_preserves_host(self):
        resolver_calls = []
        factory_calls = []
        request_calls = []

        def resolver(host, port, **kwargs):
            resolver_calls.append((host, port))
            return [_answer("93.184.216.34", port)]

        def connector(scheme, hostname, port, address, timeout, context):
            factory_calls.append((scheme, hostname, port, address, timeout, context))
            return _FakeConnection(
                _FakeResponse(headers={"Content-Type": "application/json"}, body=b'{"ok":true}'),
                request_calls,
            )

        result = fetch_public_document(
            "https://vendor.example:8443/report?b=2&a=1",
            allowed_hosts={"vendor.example"},
            _resolver=resolver,
            _connection_factory=connector,
            _ssl_context=ssl.create_default_context(),
        )
        self.assertEqual(result.body, b'{"ok":true}')
        self.assertEqual(resolver_calls, [("vendor.example", 8443)])
        self.assertEqual(factory_calls[0][0:3], ("https", "vendor.example", 8443))
        self.assertEqual(factory_calls[0][3][4], ("93.184.216.34", 8443))
        self.assertEqual(request_calls[0][0], "GET")
        self.assertEqual(request_calls[0][1], "/report?a=1&b=2")
        self.assertEqual(request_calls[0][2]["Host"], "vendor.example:8443")

    def test_https_connection_wraps_pinned_socket_for_original_hostname(self):
        address = _answer("93.184.216.34", 443)
        calls = []

        class RawSocket:
            def settimeout(self, timeout):
                calls.append(("timeout", timeout))

            def connect(self, sockaddr):
                calls.append(("connect", sockaddr))

            def close(self):
                calls.append(("close",))

        class Context:
            def wrap_socket(self, sock, *, server_hostname):
                calls.append(("wrap", sock, server_hostname))
                return "wrapped-socket"

        raw = RawSocket()
        connection = _PinnedHTTPSConnection(
            "vendor.example",
            443,
            address,
            3.0,
            Context(),
        )
        with patch("scripts.vendor_adapters.fetch.socket.socket", return_value=raw):
            connection.connect()

        self.assertIn(("connect", ("93.184.216.34", 443)), calls)
        self.assertIn(("wrap", raw, "vendor.example"), calls)
        self.assertEqual(connection.sock, "wrapped-socket")

    def test_redirect_target_is_resolved_and_rejected_before_connect(self):
        resolver_calls = []
        factory_calls = []
        request_calls = []

        def resolver(host, port, **kwargs):
            resolver_calls.append(host)
            if host == "vendor.example":
                return [_answer("93.184.216.34", port)]
            return [_answer("169.254.169.254", port)]

        def connector(scheme, hostname, port, address, timeout, context):
            factory_calls.append(hostname)
            return _FakeConnection(
                _FakeResponse(
                    status=302,
                    headers={"Location": "https://cdn.example.com/latest", "Content-Type": "text/plain"},
                ),
                request_calls,
            )

        result = fetch_public_document(
            "https://vendor.example/start",
            allowed_hosts={"vendor.example", "cdn.example.com"},
            _resolver=resolver,
            _connection_factory=connector,
        )
        self.assertEqual(resolver_calls, ["vendor.example", "cdn.example.com"])
        self.assertEqual(factory_calls, ["vendor.example"])
        self.assertIn("non-global address 169.254.169.254", result.error)
        self.assertEqual(result.redirect_chain, ("https://cdn.example.com/latest",))


if __name__ == "__main__":
    unittest.main()
