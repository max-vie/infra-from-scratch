import socket
import struct
import subprocess
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
HTTP_SERVER = ROOT / "http-server" / "server.py"
LOAD_BALANCER = ROOT / "load-balancer" / "server.py"
REVERSE_PROXY = ROOT / "reverse-proxy" / "server.py"
DNS_DIR = ROOT / "dns-server"
HOST = "127.0.0.1"
DNS_TRANSACTION_ID = 0x1234


def free_port(socket_type=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, socket_type) as temporary_socket:
        temporary_socket.bind((HOST, 0))
        return temporary_socket.getsockname()[1]


def build_dns_query():
    header = struct.pack("!HHHHHH", DNS_TRANSACTION_ID, 0x0100, 1, 0, 0, 0)
    question = b"\x03app\x05local\x00\x00\x01\x00\x01"
    return header + question


def skip_name(packet, position):
    while True:
        if position >= len(packet):
            raise ValueError("truncated DNS name")
        length = packet[position]
        if length == 0:
            return position + 1
        if length & 0xC0 == 0xC0:
            if position + 2 > len(packet):
                raise ValueError("truncated DNS pointer")
            return position + 2
        if length & 0xC0:
            raise ValueError("invalid DNS label")
        position += 1 + length


def parse_dns_address(packet):
    if len(packet) < 12:
        raise ValueError("truncated DNS response")

    transaction_id, flags, question_count, answer_count, _, _ = struct.unpack(
        "!HHHHHH", packet[:12]
    )
    if transaction_id != DNS_TRANSACTION_ID:
        raise ValueError("unexpected DNS transaction ID")
    if not flags & 0x8000 or flags & 0x000F:
        raise ValueError("DNS response was not successful")
    if question_count != 1 or answer_count < 1:
        raise ValueError("DNS response did not contain one answer")

    position = skip_name(packet, 12)
    if position + 4 > len(packet):
        raise ValueError("truncated DNS question")
    position += 4

    for _ in range(answer_count):
        position = skip_name(packet, position)
        if position + 10 > len(packet):
            raise ValueError("truncated DNS answer")
        record_type, record_class, _, data_length = struct.unpack(
            "!HHIH", packet[position:position + 10]
        )
        position += 10
        if position + data_length > len(packet):
            raise ValueError("truncated DNS answer data")
        if record_type == 1 and record_class == 1 and data_length == 4:
            return socket.inet_ntoa(packet[position:position + data_length])
        position += data_length

    raise ValueError("DNS response did not contain an IPv4 address")


def resolve_app_address(port):
    deadline = time.monotonic() + 3
    last_error = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as query_socket:
        query_socket.settimeout(0.1)
        while time.monotonic() < deadline:
            try:
                query_socket.sendto(build_dns_query(), (HOST, port))
                response, _ = query_socket.recvfrom(512)
                return parse_dns_address(response)
            except (OSError, ValueError) as error:
                last_error = error
                time.sleep(0.01)
    raise AssertionError(f"DNS server did not resolve app.local: {last_error}")


def wait_for_tcp_port(process, port):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"process exited with status {process.returncode}")
        try:
            with socket.create_connection((HOST, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.01)
    raise AssertionError(f"nothing listened on {HOST}:{port}")


def send_request(host, port):
    with socket.create_connection((host, port), timeout=2) as connection:
        connection.sendall(b"GET /health HTTP/1.1\r\nHost: app.local\r\n\r\n")
        connection.shutdown(socket.SHUT_WR)

        response = bytearray()
        while chunk := connection.recv(4096):
            response.extend(chunk)
    return bytes(response)


class TestStack(unittest.TestCase):
    def setUp(self):
        self.processes = []

    def start_process(self, *command, cwd=ROOT):
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(process)
        return process

    def tearDown(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def start_http_dns_load_balancer(self):
        backend_ports = []
        for _ in range(2):
            backend_port = free_port()
            backend_ports.append(backend_port)
            backend = self.start_process(
                sys.executable,
                str(HTTP_SERVER),
                "--host",
                HOST,
                "--port",
                str(backend_port),
            )
            wait_for_tcp_port(backend, backend_port)

        dns_port = free_port(socket.SOCK_DGRAM)
        self.start_process(
            "go",
            "run",
            "server.go",
            "-host",
            HOST,
            "-port",
            str(dns_port),
            cwd=DNS_DIR,
        )
        resolved_host = resolve_app_address(dns_port)
        self.assertEqual(resolved_host, HOST)

        load_balancer_port = free_port()
        command = [
            sys.executable,
            str(LOAD_BALANCER),
            "--listen-host",
            HOST,
            "--listen-port",
            str(load_balancer_port),
        ]
        for backend_port in backend_ports:
            command.extend(("--backend", f"{HOST}:{backend_port}"))
        load_balancer = self.start_process(*command)
        wait_for_tcp_port(load_balancer, load_balancer_port)

        return resolved_host, load_balancer_port

    def test_dns_load_balancer_and_http_servers_work_together(self):
        resolved_host, load_balancer_port = self.start_http_dns_load_balancer()

        responses = [
            send_request(resolved_host, load_balancer_port) for _ in range(2)
        ]
        for response in responses:
            self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
            self.assertIn(b"OK\n", response)

    def test_dns_reverse_proxy_load_balancer_and_http_servers_work_together(self):
        resolved_host, load_balancer_port = self.start_http_dns_load_balancer()

        proxy_port = free_port()
        proxy = self.start_process(
            sys.executable,
            str(REVERSE_PROXY),
            "--listen-host",
            HOST,
            "--listen-port",
            str(proxy_port),
            "--backend-host",
            HOST,
            "--backend-port",
            str(load_balancer_port),
        )
        wait_for_tcp_port(proxy, proxy_port)

        response = send_request(resolved_host, proxy_port)

        self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
        self.assertIn(b"OK\n", response)


if __name__ == "__main__":
    unittest.main()
