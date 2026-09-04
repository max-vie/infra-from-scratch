import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path


# Add the parent directory so the test can import client.py directly.
sys.path.insert(0, str(Path(__file__).parents[1]))

from client import Response, URL


class OneShotResponseServer:
    def __init__(self, response):
        self.response = response
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
                    connection.recv(4096)
                    connection.sendall(self.response)
        except OSError:
            pass


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

    def test_rejects_https(self): # Remove/refactor after tls integration 
        with self.assertRaises(ValueError):
            URL("https://localhost:8088/")


if __name__ == "__main__":
    unittest.main()
