from __future__ import annotations

import socket
import unittest

from scripts.vendor_adapters.fetch import fetch_public_document


def _answer(address: str, port: int):
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))


class _FakeResponse:
    def __init__(self, status: int, headers=None, body: bytes = b"unexpected-body") -> None:
        self.status = status
        self._headers = dict(headers or {})
        self._body = body
        self.read_calls = 0
        self.closed = False

    def getheader(self, name, default=None):
        for key, value in self._headers.items():
            if key.lower() == name.lower():
                return value
        return default

    def read(self, amount=-1):
        self.read_calls += 1
        return self._body if amount < 0 else self._body[:amount]

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.closed = False

    def request(self, method, target, body=None, headers=None):
        return None

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class FetchTerminalStatusTests(unittest.TestCase):
    def fetch(self, response: _FakeResponse):
        connection = _FakeConnection(response)

        def resolver(host, port, **kwargs):
            return [_answer("93.184.216.34", port)]

        def connector(*args):
            return connection

        result = fetch_public_document(
            "https://vendor.example/document",
            allowed_hosts={"vendor.example"},
            _resolver=resolver,
            _connection_factory=connector,
        )
        return result, connection

    def test_terminal_http_errors_return_empty_body_without_reading(self):
        for status in (404, 500):
            with self.subTest(status=status):
                response = _FakeResponse(
                    status,
                    headers={"Content-Type": "text/html"},
                    body=b"vendor error page",
                )
                result, connection = self.fetch(response)
                self.assertEqual(result.status, status)
                self.assertEqual(result.body, b"")
                self.assertEqual(result.content_type, "")
                self.assertEqual(result.error, f"http_status_{status}")
                self.assertEqual(response.read_calls, 0)
                self.assertTrue(response.closed)
                self.assertTrue(connection.closed)

    def test_redirect_without_location_is_terminal_error(self):
        response = _FakeResponse(302, headers={"Content-Type": "text/plain"})
        result, _ = self.fetch(response)
        self.assertEqual(result.status, 302)
        self.assertEqual(result.body, b"")
        self.assertEqual(result.error, "http_status_302")
        self.assertEqual(result.redirect_chain, ())
        self.assertEqual(response.read_calls, 0)

    def test_no_content_remains_successful(self):
        response = _FakeResponse(204, body=b"")
        result, _ = self.fetch(response)
        self.assertEqual(result.status, 204)
        self.assertEqual(result.body, b"")
        self.assertEqual(result.error, "")
        self.assertEqual(response.read_calls, 1)


if __name__ == "__main__":
    unittest.main()
