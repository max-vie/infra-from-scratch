import contextlib
import io
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVER_DIR))

from server import MAX_REQUEST_SIZE, parse_args


HOST = "127.0.0.1"
BACKEND_SCRIPT = r"""
import socket
import sys

port = int(sys.argv[1])
body = sys.argv[2].encode("ascii")
response = (
    b"HTTP/1.1 200 OK\r\n"
    + f"Content-Length: {len(body)}\r\n".encode("ascii")
    + b"Connection: close\r\n"
    + b"\r\n"
    + body
)

with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(5)
    while True:
        connection, _ = listener.accept()
        with connection:
            request = bytearray()
            while b"\r\n\r\n" not in request:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                request.extend(chunk)
            if request:
                connection.sendall(response)
"""
PARTIAL_BACKEND_SCRIPT = r"""
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
        connection.sendall(b"HTTP/1.1 200 OK\r\n")
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


class TestLoadBalancer(unittest.TestCase):
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

    def start_backend(self, body):
        backend_port = free_port()
        self.start_process(
            sys.executable,
            "-c",
            BACKEND_SCRIPT,
            str(backend_port),
            body,
        )
        wait_for_port(backend_port)
        return HOST, backend_port

    def start_load_balancer(self, backends):
        load_balancer_port = free_port()
        command = [
            sys.executable,
            "load-balancer/server.py",
            "--listen-host",
            HOST,
            "--listen-port",
            str(load_balancer_port),
        ]
        for host, port in backends:
            command.extend(("--backend", f"{host}:{port}"))
        self.start_process(*command)
        wait_for_port(load_balancer_port)
        return load_balancer_port

    def request(self, load_balancer_port, request):
        # Send one request and read until the load balancer closes the connection.
        with socket.create_connection(
            (HOST, load_balancer_port),
            timeout=2,
        ) as connection:
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

    def test_round_robins_between_two_backends(self):
        backends = [
            self.start_backend("backend-a"),
            self.start_backend("backend-b"),
        ]
        load_balancer_port = self.start_load_balancer(backends)
        request = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"

        responses = [
            self.request(load_balancer_port, request)
            for _ in range(3)
        ]

        self.assertIn(b"backend-a", responses[0])
        self.assertIn(b"backend-b", responses[1])
        self.assertIn(b"backend-a", responses[2])

    def test_fails_over_to_other_backend_on_connection_failure(self):
        live_backend = self.start_backend("backend-b")
        unavailable_backend = (HOST, free_port())
        load_balancer_port = self.start_load_balancer(
            [unavailable_backend, live_backend]
        )
        request = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"

        first_response = self.request(load_balancer_port, request)
        second_response = self.request(load_balancer_port, request)

        self.assertIn(b"backend-b", first_response)
        self.assertIn(b"backend-b", second_response)

    def test_returns_bad_gateway_when_both_backends_unavailable(self):
        backends = [(HOST, free_port()), (HOST, free_port())]
        load_balancer_port = self.start_load_balancer(backends)
        request = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"

        response = self.request(load_balancer_port, request)

        self.assertIn(b"HTTP/1.0 502 Bad Gateway", response)

    def test_rejects_invalid_requests_before_backend_selection(self):
        backends = [(HOST, free_port()), (HOST, free_port())]
        load_balancer_port = self.start_load_balancer(backends)
        requests = (
            b"",
            b"GET / HTTP/1.1\r\nHost: localhost\r\n",
            b"POST / HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Length: 4\r\n\r\nbody",
            b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Large: "
            + b"x" * MAX_REQUEST_SIZE
            + b"\r\n\r\n",
        )

        for request in requests:
            with self.subTest(request=request[:30]):
                response = self.request(load_balancer_port, request)
                self.assertIn(b"HTTP/1.0 400 Bad Request", response)

    def test_rejects_invalid_configuration(self):
        cases = (
            [],
            ["--backend", "127.0.0.1:8088"],
            ["--backend", "127.0.0.1:8088", "--backend", "bad"],
            [
                "--listen-port",
                "0",
                "--backend",
                "127.0.0.1:8088",
                "--backend",
                "127.0.0.1:8089",
            ],
        )

        for arguments in cases:
            with self.subTest(arguments=arguments):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parse_args(arguments)

    def test_does_not_append_bad_gateway_after_partial_response(self):
        backend_port = free_port()
        self.start_process(
            sys.executable,
            "-c",
            PARTIAL_BACKEND_SCRIPT,
            str(backend_port),
        )
        wait_for_port(backend_port)
        load_balancer_port = self.start_load_balancer(
            [(HOST, backend_port), (HOST, free_port())]
        )

        response = self.request(
            load_balancer_port,
            b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )

        self.assertEqual(response, b"HTTP/1.1 200 OK\r\n")


if __name__ == "__main__":
    unittest.main()
