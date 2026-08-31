import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVER_DIR))

from server import MAX_REQUEST_SIZE, parse_headers, parse_request_line


HOST = "127.0.0.1"
PORT = 8088


def wait_for_port(port):
    # Wait until the server accepts TCP connections.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.01)
    raise AssertionError(f"nothing listened on {HOST}:{port}")


def send_request(parts):
    # Send one request and read until the server closes the connection.
    with socket.create_connection((HOST, PORT), timeout=2) as connection:
        for part in parts:
            connection.sendall(part)
        connection.shutdown(socket.SHUT_WR)

        response = bytearray()
        while chunk := connection.recv(4096):
            response.extend(chunk)
    return bytes(response)


class TestRequestParsing(unittest.TestCase):
    def test_parses_request_line(self):
        self.assertEqual(
            parse_request_line(b"GET /hello HTTP/1.1"),
            ("GET", "/hello", "HTTP/1.1"),
        )

    def test_rejects_malformed_request_lines(self):
        for line in (
            b"GET /hello",
            b"GET /hello HTTP/2.0",
            b"GET hello HTTP/1.1",
        ):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    parse_request_line(line)

    def test_parses_case_insensitive_headers(self):
        headers = parse_headers(
            b"Host: app.local\r\nConnection: close"
        )

        self.assertEqual(
            headers,
            {"host": "app.local", "connection": "close"},
        )

    def test_rejects_malformed_or_duplicate_headers(self):
        for header_block in (
            b"Host app.local",
            b": app.local",
            b"Host: app.local\r\nhost: other.local",
        ):
            with self.subTest(header_block=header_block):
                with self.assertRaises(ValueError):
                    parse_headers(header_block)


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start one server for the socket-level behavior tests.
        cls.server = subprocess.Popen(
            [sys.executable, "http-server/server.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_port(PORT)

    @classmethod
    def tearDownClass(cls):
        # Always stop the server started by this test class.
        if cls.server.poll() is None:
            cls.server.terminate()
            try:
                cls.server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait()

    def test_returns_successful_routes(self):
        routes = {
            "/": b"HELLO WORLD!\n",
            "/health": b"OK\n",
            "/hello": b"HELLO WORLD!\n",
        }
        for path, body in routes.items():
            with self.subTest(path=path):
                response = send_request(
                    [
                        f"GET {path} HTTP/1.1\r\n".encode("ascii"),
                        b"Host: app.local\r\n\r\n",
                    ]
                )

                self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
                self.assertIn(body, response)
                self.assertIn(f"Content-Length: {len(body)}".encode(), response)
                self.assertIn(b"Connection: close\r\n", response)

    def test_reads_until_header_terminator(self):
        response = send_request(
            [
                b"GET /hello HTTP/1.1\r\nHost: app.local",
                b"\r\n\r\n",
            ]
        )

        self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
        self.assertIn(b"HELLO WORLD!\n", response)

    def test_returns_not_found_for_unknown_route(self):
        response = send_request(
            [b"GET /missing HTTP/1.1\r\nHost: app.local\r\n\r\n"]
        )

        self.assertIn(b"HTTP/1.1 404 Not Found\r\n", response)
        self.assertIn(b"Not Found\n", response)

    def test_returns_method_not_allowed_for_non_get(self):
        response = send_request(
            [b"POST /hello HTTP/1.1\r\nHost: app.local\r\n\r\n"]
        )

        self.assertIn(b"HTTP/1.1 405 Method Not Allowed\r\n", response)
        self.assertIn(b"Allow: GET\r\n", response)

    def test_returns_bad_request_for_malformed_request(self):
        requests = (
            b"GET / HTTP/1.1\r\nHost app.local\r\n\r\n",
            b"GET / HTTP/2.0\r\nHost: app.local\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: app.local\r\nContent-Length: 0\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: app.local\r\nTransfer-Encoding: chunked\r\n\r\n",
        )
        for request in requests:
            with self.subTest(request=request):
                response = send_request([request])
                self.assertIn(b"HTTP/1.1 400 Bad Request\r\n", response)

    def test_returns_bad_request_for_incomplete_headers(self):
        response = send_request([b"GET / HTTP/1.1\r\nHost: app.local\r\n"])

        self.assertIn(b"HTTP/1.1 400 Bad Request\r\n", response)

    def test_returns_bad_request_for_oversized_headers(self):
        request = (
            b"GET / HTTP/1.1\r\nHost: app.local\r\nX-Large: "
            + b"x" * MAX_REQUEST_SIZE
            + b"\r\n\r\n"
        )

        response = send_request([request])

        self.assertIn(b"HTTP/1.1 400 Bad Request\r\n", response)


if __name__ == "__main__":
    unittest.main()
