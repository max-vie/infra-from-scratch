import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path


# Add the parent directory so the test can import client.py directly.
sys.path.insert(0, str(Path(__file__).parents[1]))

from client import DNSResolver, Response, URL


class OneShotResponseServer:
    def __init__(self, response, delay=0):
        self.response = response
        self.delay = delay
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.listener.close()
        self.thread.join(timeout=2)

    def _serve(self):
        try:
            with self.listener:
                connection, _ = self.listener.accept()
                with connection:
                    self.request = connection.recv(4096)
                    time.sleep(self.delay)
                    connection.sendall(self.response)
        except OSError:
            pass


class OneShotDNSResponseServer:
    def __init__(self, response_factory):
        self.response_factory = response_factory
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener.bind(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.listener.close()
        self.thread.join(timeout=2)

    def _serve(self):
        try:
            with self.listener:
                query, address = self.listener.recvfrom(512)
                self.listener.sendto(self.response_factory(query), address)
        except OSError:
            pass


def build_dns_response(query, flags=0x8180, answer=True):
    position = 12
    while query[position] != 0:
        position += 1 + query[position]
    question_end = position + 5
    question = query[12:question_end]
    answer_count = 1 if answer else 0
    header = query[:2] + struct.pack("!HHHHH", flags, 1, answer_count, 0, 0)
    if not answer:
        return header + question
    record = (
        b"\xc0\x0c"
        + struct.pack("!HHIH", 1, 1, 60, 4)
        + b"\x7f\x00\x00\x01"
    )
    return header + question + record


class TestHTTP(unittest.TestCase):
    def test_client_requests_server(self):
        # Start the server.
        server = subprocess.Popen(
            [sys.executable, "http-server/server.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            time.sleep(0.2)
            response = URL("localhost:8088/").request()
            self.assertIsInstance(response, Response)
            self.assertEqual(response.version, "HTTP/1.1")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.reason, "OK")
            self.assertEqual(response.headers["content-length"], "13")
            self.assertEqual(response.headers["connection"], "close")
            self.assertEqual(response.body, b"HELLO WORLD!\n")

            completed = subprocess.run(
                [sys.executable, "http-server/client.py", "localhost:8088/"],
                capture_output=True,
                check=True,
            )
            self.assertEqual(completed.stdout, b"HELLO WORLD!\n")
        finally:
            # Always stop the server after the test.
            server.terminate()
            server.wait()

    def test_returns_full_response_for_non_success_status(self):
        raw_response = (
            b"HTTP/1.1 404 Not Found\r\n"
            b"X-Test: first\r\n"
            b"x-test: second\r\n"
            b"Content-Length: 3\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"no!"
        )

        with OneShotResponseServer(raw_response) as server:
            response = URL(f"127.0.0.1:{server.port}/missing").request()

        self.assertEqual(response.version, "HTTP/1.1")
        self.assertEqual(response.status, 404)
        self.assertEqual(response.reason, "Not Found")
        self.assertEqual(response.headers["x-test"], "second")
        self.assertEqual(response.body, b"no!")

    def test_resolver_returns_ipv4_address(self):
        with OneShotDNSResponseServer(build_dns_response) as server:
            resolver = DNSResolver(("127.0.0.1", server.port))
            self.assertEqual(resolver.resolve("app.local"), "127.0.0.1")

    def test_resolver_rejects_invalid_responses(self):
        responses = (
            lambda query: build_dns_response(query, flags=0x8183, answer=False),
            lambda query: build_dns_response(query, answer=False),
            lambda query: bytes([query[0] ^ 1, query[1]]) + build_dns_response(query)[2:],
            lambda query: query[:2],
        )

        for response_factory in responses:
            with self.subTest(response_factory=response_factory):
                with OneShotDNSResponseServer(response_factory) as server:
                    resolver = DNSResolver(("127.0.0.1", server.port))
                    with self.assertRaises(ValueError):
                        resolver.resolve("app.local")

    def test_request_uses_resolver_and_preserves_host_header(self):
        raw_response = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nbody"

        class StaticResolver:
            def __init__(self):
                self.host = None

            def resolve(self, host):
                self.host = host
                return "127.0.0.1"

        resolver = StaticResolver()
        with OneShotResponseServer(raw_response) as server:
            response = URL(f"app.local:{server.port}/health").request(
                resolver=resolver
            )

        self.assertEqual(response.body, b"body")
        self.assertEqual(resolver.host, "app.local")
        self.assertIn(
            f"Host: app.local:{server.port}\r\n".encode(),
            server.request,
        )

    def test_preserves_binary_response_body(self):
        raw_response = (
            b"HTTP/1.0 200 OK\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            b"\x00\xff\x80body"
        )

        with OneShotResponseServer(raw_response) as server:
            response = URL(f"127.0.0.1:{server.port}/binary").request()

        self.assertEqual(response.body, b"\x00\xff\x80body")

    def test_rejects_empty_or_malformed_responses(self):
        responses = (
            b"",
            b"HTTP/2.0 200 OK\r\n\r\n",
            b"HTTP/1.1 nope OK\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nBroken\r\n\r\n",
        )

        for raw_response in responses:
            with self.subTest(raw_response=raw_response):
                with OneShotResponseServer(raw_response) as server:
                    with self.assertRaises(ValueError):
                        URL(f"127.0.0.1:{server.port}/").request()

    def test_rejects_unsupported_response_encodings(self):
        for header in (b"Transfer-Encoding: chunked", b"Content-Encoding: gzip"):
            with self.subTest(header=header):
                raw_response = (
                    b"HTTP/1.1 200 OK\r\n"
                    + header
                    + b"\r\n\r\n"
                )
                with OneShotResponseServer(raw_response) as server:
                    with self.assertRaises(NotImplementedError):
                        URL(f"127.0.0.1:{server.port}/").request()

    def test_connection_refused(self):
        # Find a local port and close it before making the request.
        with socket.socket() as temporary_socket:
            temporary_socket.bind(("127.0.0.1", 0))
            closed_port = temporary_socket.getsockname()[1]

        with self.assertRaises(ConnectionRefusedError):
            URL(f"127.0.0.1:{closed_port}/").request()

    def test_request_times_out_when_server_stalls(self):
        with OneShotResponseServer(b"", delay=0.1) as server:
            with self.assertRaises(TimeoutError):
                URL(f"127.0.0.1:{server.port}/").request(timeout=0.01)

    def test_rejects_https(self): # Remove/refactor after tls integration 
        with self.assertRaises(ValueError):
            URL("https://localhost:8088/")


if __name__ == "__main__":
    unittest.main()
