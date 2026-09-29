import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "http-server"))

from cache_client import CacheClient
from client import DNSResolver, URL
from server import CACHE_KEY


HTTP_DIR = ROOT / "http-server"
LOAD_BALANCER_DIR = ROOT / "load-balancer"
REVERSE_PROXY_DIR = ROOT / "reverse-proxy"
DNS_DIR = ROOT / "dns-server"
CACHE_SOURCE = ROOT / "in-mem-cache" / "server.c"
RUNTIME_SOURCE = ROOT / "container-runtime" / "runtime.c"
HOST = "127.0.0.1"


def free_port(socket_type=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, socket_type) as temporary_socket:
        temporary_socket.bind((HOST, 0))
        return temporary_socket.getsockname()[1]


def resolve_app_address(resolver):
    deadline = time.monotonic() + 3
    last_error = None
    while time.monotonic() < deadline:
        try:
            return resolver.resolve("app.local")
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


def wait_for_backend_registration(registry_port, address, present=True):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with urllib.request.urlopen(
            f"http://{HOST}:{registry_port}/backends", timeout=1
        ) as response:
            addresses = response.read().decode("ascii").splitlines()
        if (address in addresses) == present:
            return
        time.sleep(0.05)
    raise AssertionError(f"backend {address} registration did not become {present}")


class TestStack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build_dir.cleanup)
        cls.cache_binary = Path(cls.build_dir.name) / "cache-server"
        cls.runtime_binary = Path(os.environ.get(
            "CONTAINER_RUNTIME_TEST_BINARY", str(Path(cls.build_dir.name) / "runtime")
        )).resolve()
        subprocess.run(
            [
                "gcc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-O2",
                "-pthread",
                "-o",
                str(cls.cache_binary),
                str(CACHE_SOURCE),
            ],
            check=True,
        )
        subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-O2", "-o", str(cls.runtime_binary), str(RUNTIME_SOURCE)],
            check=True,
        )
        cls.cache_rootfs = Path(cls.build_dir.name) / "cache-rootfs"
        (cls.cache_rootfs / "proc").mkdir(parents=True)
        shutil.copy2(cls.cache_binary, cls.cache_rootfs / "cache-server")
        # Resolve libraries only for the freshly compiled, trusted cache binary.
        linked = subprocess.run(
            ["ldd", str(cls.cache_binary)], capture_output=True, text=True, check=True,
            env={**os.environ, "LC_ALL": "C"},
        ).stdout
        for library in set(re.findall(r"(/[\w/+.\-]+)", linked)):
            destination = cls.cache_rootfs / library.lstrip("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(library, destination)

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

    def start_cache(self):
        cache_port = free_port()
        cache = self.start_process(
            str(self.runtime_binary),
            str(self.cache_rootfs),
            "/cache-server",
            "--listen-host",
            HOST,
            "--listen-port",
            str(cache_port),
        )
        wait_for_tcp_port(cache, cache_port)
        return cache_port, cache

    def start_http_backend(self, cache_port=None, registry_port=None):
        backend_port = free_port()
        while backend_port == registry_port:
            backend_port = free_port()
        command = [
            sys.executable,
            "server.py",
            "--host",
            HOST,
            "--port",
            str(backend_port),
        ]
        if cache_port is not None:
            command.extend(("--cache-host", HOST, "--cache-port", str(cache_port)))
        if registry_port is not None:
            command.extend(("--registry-port", str(registry_port)))
        backend = self.start_process(*command, cwd=HTTP_DIR)
        wait_for_tcp_port(backend, backend_port)
        return backend_port, backend

    def start_http_dns_load_balancer(self, cache_available=True):
        cache_port = self.start_cache()[0] if cache_available else free_port()
        backend_ports = []
        for _ in range(2):
            backend_port, _ = self.start_http_backend(cache_port=cache_port)
            backend_ports.append(backend_port)

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
        resolver = DNSResolver((HOST, dns_port))
        self.assertEqual(resolve_app_address(resolver), HOST)

        load_balancer_port = free_port()
        command = [
            "go",
            "run",
            "server.go",
            "-listen-host",
            HOST,
            "-listen-port",
            str(load_balancer_port),
        ]
        for backend_port in backend_ports:
            command.extend(("-backend", f"{HOST}:{backend_port}"))
        load_balancer = self.start_process(*command, cwd=LOAD_BALANCER_DIR)
        wait_for_tcp_port(load_balancer, load_balancer_port)

        return resolver, load_balancer_port, cache_port

    def start_reverse_proxy(self, load_balancer_port):
        proxy_port = free_port()
        proxy = self.start_process(
            "go",
            "run",
            "server.go",
            "-listen-host",
            HOST,
            "-listen-port",
            str(proxy_port),
            "-backend-host",
            HOST,
            "-backend-port",
            str(load_balancer_port),
            cwd=REVERSE_PROXY_DIR,
        )
        wait_for_tcp_port(proxy, proxy_port)
        return proxy_port

    def test_dns_load_balancer_and_http_servers_work_together(self):
        resolver, load_balancer_port, _ = self.start_http_dns_load_balancer()

        responses = [
            URL(f"app.local:{load_balancer_port}/health").request(
                resolver=resolver
            )
            for _ in range(2)
        ]
        for response in responses:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, b"OK\n")

    def test_dns_reverse_proxy_load_balancer_and_http_servers_work_together(self):
        resolver, load_balancer_port, _ = self.start_http_dns_load_balancer()
        proxy_port = self.start_reverse_proxy(load_balancer_port)

        response = URL(f"app.local:{proxy_port}/health").request(
            resolver=resolver
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"OK\n")

    def test_cache_populates_and_serves_cached_body_through_full_path(self):
        resolver, load_balancer_port, cache_port = (
            self.start_http_dns_load_balancer()
        )
        proxy_port = self.start_reverse_proxy(load_balancer_port)
        cache = CacheClient(HOST, cache_port)

        self.assertIsNone(cache.get(CACHE_KEY))
        first = URL(f"app.local:{proxy_port}/hello").request(
            resolver=resolver
        )
        self.assertEqual(first.status, 200)
        self.assertEqual(first.body, b"HELLO WORLD!\n")
        self.assertEqual(cache.get(CACHE_KEY), b"HELLO WORLD!")

        cache.set(CACHE_KEY, b"CACHED", 0)
        second = URL(f"app.local:{proxy_port}/hello").request(
            resolver=resolver
        )
        self.assertEqual(second.status, 200)
        self.assertEqual(second.body, b"CACHED\n")

    def test_unavailable_cache_does_not_break_full_path(self):
        resolver, load_balancer_port, _ = self.start_http_dns_load_balancer(
            cache_available=False
        )
        proxy_port = self.start_reverse_proxy(load_balancer_port)

        response = URL(f"app.local:{proxy_port}/hello").request(
            resolver=resolver
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"HELLO WORLD!\n")

    def test_cache_container_shutdown_releases_processes_and_listener(self):
        cache_port, launcher = self.start_cache()
        init_children = Path(
            f"/proc/{launcher.pid}/task/{launcher.pid}/children"
        ).read_text().split()
        self.assertEqual(len(init_children), 1)
        init_pid = int(init_children[0])
        cache_children = Path(f"/proc/{init_pid}/task/{init_pid}/children").read_text().split()
        self.assertEqual(len(cache_children), 1)
        cache_pid = int(cache_children[0])
        self.assertTrue(os.path.samefile(f"/proc/{cache_pid}/root", self.cache_rootfs))
        for namespace in ("pid", "mnt"):
            self.assertNotEqual(
                os.stat(f"/proc/{cache_pid}/ns/{namespace}").st_ino,
                os.stat(f"/proc/self/ns/{namespace}").st_ino,
            )

        with socket.create_connection((HOST, cache_port), timeout=1) as client:
            client.sendall(b"GET missing\n")
            with client.makefile("rb") as reply:
                self.assertEqual(reply.readline(), b"NOT_FOUND\n")
            self.assertGreaterEqual(len(list(Path(f"/proc/{cache_pid}/task").iterdir())), 2)
            launcher.terminate()
            self.assertEqual(launcher.wait(timeout=2), 143)
            try:
                self.assertEqual(client.recv(4096), b"")
            except ConnectionResetError:
                pass

        for pid in (init_pid, cache_pid):
            self.assertFalse(Path(f"/proc/{pid}").exists(), f"cache process {pid} remains")
        with socket.socket() as closed_listener:
            closed_listener.settimeout(1)
            with self.assertRaises(ConnectionRefusedError):
                closed_listener.connect((HOST, cache_port))
        with socket.socket() as replacement:
            replacement.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            replacement.bind((HOST, cache_port))
        self.assertFalse(os.path.ismount(self.cache_rootfs))
        self.assertEqual(list((self.cache_rootfs / "proc").iterdir()), [])

    def test_backend_registration_changes_the_full_path(self):
        registry_port = free_port()
        first_port, first = self.start_http_backend(registry_port=registry_port)
        balancer_port = free_port()
        while balancer_port == registry_port:
            balancer_port = free_port()
        balancer = self.start_process(
            "go", "run", "server.go",
            "-listen-host", HOST,
            "-listen-port", str(balancer_port),
            "-registry-port", str(registry_port),
            cwd=LOAD_BALANCER_DIR,
        )
        wait_for_tcp_port(balancer, balancer_port)
        wait_for_tcp_port(balancer, registry_port)

        dns_port = free_port(socket.SOCK_DGRAM)
        self.start_process(
            "go", "run", "server.go", "-host", HOST, "-port", str(dns_port),
            cwd=DNS_DIR,
        )
        resolver = DNSResolver((HOST, dns_port))
        self.assertEqual(resolve_app_address(resolver), HOST)
        proxy_port = self.start_reverse_proxy(balancer_port)
        url = URL(f"app.local:{proxy_port}/health")

        wait_for_backend_registration(registry_port, f"{HOST}:{first_port}")
        self.assertEqual(url.request(resolver=resolver).body, b"OK\n")
        time.sleep(3.2)
        wait_for_backend_registration(registry_port, f"{HOST}:{first_port}")

        second_port, _ = self.start_http_backend(registry_port=registry_port)
        wait_for_backend_registration(registry_port, f"{HOST}:{second_port}")
        first.terminate()
        first.wait(timeout=2)
        wait_for_backend_registration(registry_port, f"{HOST}:{first_port}", present=False)
        self.assertEqual(url.request(resolver=resolver).body, b"OK\n")


if __name__ == "__main__":
    unittest.main()
