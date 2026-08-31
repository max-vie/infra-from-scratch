import socket
import subprocess
import sys
import time
import unittest


BACKEND_PORT = 8088
HOST = "127.0.0.1"
PARTIAL_BACKEND_SCRIPT = """
import socket
import struct
import sys

with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", int(sys.argv[1])))
    listener.listen(2)
    with listener.accept()[0]:
        pass
    connection, _ = listener.accept()
    with connection:
        connection.recv(4096)
        connection.sendall(b"HTTP/1.1 200 OK\\r\\n")
        connection.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_LINGER,
            struct.pack("ii", 1, 0),
        )
"""


def free_port():
    # Ask the operating system for an unused local port.
    with socket.socket() as temporary_socket:
        temporary_socket.bind((HOST, 0))
        return temporary_socket.getsockname()[1]


def wait_for_port(port):
    # Wait until a subprocess accepts TCP connections.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.01)
    raise AssertionError(f"nothing listened on {HOST}:{port}")


class TestReverseProxy(unittest.TestCase):
    def setUp(self):
        self.processes = []

    def start_process(self, *command):
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(process)
        return process

    def start_proxy(self, backend_port, listen_host=HOST):
        proxy_port = free_port()
        self.start_process(
            sys.executable,
            "reverse-proxy/server.py",
            "--listen-host",
            listen_host,
            "--listen-port",
            str(proxy_port),
            "--backend-port",
            str(backend_port),
        )
        wait_for_port(proxy_port)
        return proxy_port

    def test_binds_explicit_listener_addresses(self):
        for listen_host in ("127.0.0.1", "0.0.0.0"):
            with self.subTest(listen_host=listen_host):
                proxy_port = self.start_proxy(free_port(), listen_host)
                response = self.request(
                    proxy_port,
                    b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n",
                )

                self.assertIn(b"HTTP/1.0 502 Bad Gateway", response)

    def test_rejects_invalid_port_configuration(self):
        for option, value in (
            ("--listen-port", "0"),
            ("--backend-port", "65536"),
            ("--listen-port", "not-a-port"),
        ):
            with self.subTest(option=option, value=value):
                result = subprocess.run(
                    [
                        sys.executable,
                        "reverse-proxy/server.py",
                        option,
                        value,
                    ],
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)

    def request(self, proxy_port, request):
        # Send one request and read until the proxy closes the connection.
        with socket.create_connection((HOST, proxy_port), timeout=2) as connection:
            connection.sendall(request)
            connection.shutdown(socket.SHUT_WR)

            response = bytearray()
            while chunk := connection.recv(4096):
                response.extend(chunk)
        return bytes(response)

    def tearDown(self):
        # Always stop subprocesses started by the test.
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def test_forwards_request_to_backend(self):
        # Use the existing HTTP server as the backend.
        self.start_process(sys.executable, "http-server/server.py")
        wait_for_port(BACKEND_PORT)
        proxy_port = self.start_proxy(BACKEND_PORT)

        response = self.request(
            proxy_port,
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )

        self.assertIn(b"HTTP/1.1 200 OK", response)
        self.assertIn(b"HELLO WORLD!", response)

    def test_returns_bad_gateway_when_backend_is_unavailable(self):
        proxy_port = self.start_proxy(free_port())

        response = self.request(
            proxy_port,
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )

        self.assertIn(b"HTTP/1.0 502 Bad Gateway", response)
        self.assertIn(b"Bad Gateway\n", response)

    def test_returns_bad_request_for_incomplete_headers(self):
        proxy_port = self.start_proxy(free_port())

        response = self.request(
            proxy_port,
            b"GET / HTTP/1.1\r\nHost: localhost\r\n",
        )

        self.assertIn(b"HTTP/1.0 400 Bad Request", response)
        self.assertIn(b"Bad Request\n", response)

    def test_returns_bad_request_for_oversized_headers(self):
        proxy_port = self.start_proxy(free_port())
        request = (
            b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Large: "
            + b"x" * (64 * 1024)
            + b"\r\n\r\n"
        )

        response = self.request(proxy_port, request)

        self.assertIn(b"HTTP/1.0 400 Bad Request", response)

    def test_rejects_requests_that_advertise_bodies(self):
        proxy_port = self.start_proxy(free_port())

        for header in (b"Content-Length: 4", b"Transfer-Encoding: chunked"):
            with self.subTest(header=header):
                response = self.request(
                    proxy_port,
                    b"POST / HTTP/1.1\r\nHost: localhost\r\n"
                    + header
                    + b"\r\n\r\nbody",
                )

                self.assertIn(b"HTTP/1.0 400 Bad Request", response)

    def test_does_not_append_bad_gateway_after_partial_response(self):
        backend_port = free_port()
        self.start_process(
            sys.executable,
            "-c",
            PARTIAL_BACKEND_SCRIPT,
            str(backend_port),
        )
        wait_for_port(backend_port)
        proxy_port = self.start_proxy(backend_port)

        response = self.request(
            proxy_port,
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )

        self.assertEqual(response, b"HTTP/1.1 200 OK\r\n")

    def test_returns_bad_request_for_empty_request(self):
        proxy_port = self.start_proxy(free_port())

        response = self.request(proxy_port, b"")

        self.assertIn(b"HTTP/1.0 400 Bad Request", response)


if __name__ == "__main__":
    unittest.main()
