import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).parents[1]
SERVER_SRC = SERVER_DIR / "server.c"

HOST = "127.0.0.1"


def free_port():
    # Ask the operating system for an unused local port.
    with socket.socket() as temporary_socket:
        temporary_socket.bind((HOST, 0))
        return temporary_socket.getsockname()[1]


def wait_for_port(port):
    # Wait until the cache accepts TCP connections.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.01)
    raise AssertionError(f"nothing listened on {HOST}:{port}")


class CacheConnection:
    # Keep one TCP connection open for several cache commands.

    def __init__(self, port):
        self.socket = socket.create_connection((HOST, port), timeout=2)
        self.file = self.socket.makefile("rwb")

    def command(self, line):
        # Send one newline-terminated command and read one reply line.
        if not line.endswith(b"\n"):
            line += b"\n"
        self.file.write(line)
        self.file.flush()
        return self.file.readline()

    def close(self):
        try:
            self.file.close()
        finally:
            self.socket.close()


class TestInMemCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = tempfile.TemporaryDirectory()
        cls.server_bin = Path(cls.build_dir.name) / "server"
        subprocess.run(
            [
                "gcc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-O2",
                "-o",
                str(cls.server_bin),
                str(SERVER_SRC),
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.build_dir.cleanup()

    def setUp(self):
        self.processes = []

    def start_cache(self):
        cache_port = free_port()
        process = subprocess.Popen(
            [
                str(self.server_bin),
                "--listen-host",
                HOST,
                "--listen-port",
                str(cache_port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.processes.append(process)
        wait_for_port(cache_port)
        return cache_port

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

    def test_set_and_get_roundtrip(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"SET foo 0 bar\r\n"), b"OK\n")
            self.assertEqual(connection.command(b"GET foo\r\n"), b"VALUE bar\n")
        finally:
            connection.close()

    def test_get_missing_key_returns_not_found(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"GET missing"), b"NOT_FOUND\n")
        finally:
            connection.close()

    def test_delete_removes_key(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"SET foo 0 bar"), b"OK\n")
            self.assertEqual(connection.command(b"DELETE foo"), b"OK\n")
            self.assertEqual(connection.command(b"GET foo"), b"NOT_FOUND\n")
        finally:
            connection.close()

    def test_delete_missing_key_returns_not_found(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"DELETE missing"), b"NOT_FOUND\n")
        finally:
            connection.close()

    def test_set_overwrites_value(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"SET foo 0 one"), b"OK\n")
            self.assertEqual(connection.command(b"SET foo 0 two"), b"OK\n")
            self.assertEqual(connection.command(b"GET foo"), b"VALUE two\n")
        finally:
            connection.close()

    def test_expired_key_behaves_as_missing(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"SET tmp 1 quick"), b"OK\n")
            self.assertEqual(connection.command(b"GET tmp"), b"VALUE quick\n")
            time.sleep(1.2)
            self.assertEqual(connection.command(b"GET tmp"), b"NOT_FOUND\n")
        finally:
            connection.close()

    def test_zero_ttl_does_not_expire(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"SET foo 0 bar"), b"OK\n")
            time.sleep(1.1)
            self.assertEqual(connection.command(b"GET foo"), b"VALUE bar\n")
        finally:
            connection.close()

    def test_overwrite_clears_expiry(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(connection.command(b"SET foo 1 quick"), b"OK\n")
            self.assertEqual(connection.command(b"SET foo 0 kept"), b"OK\n")
            time.sleep(1.2)
            self.assertEqual(connection.command(b"GET foo"), b"VALUE kept\n")
        finally:
            connection.close()

    def test_value_may_contain_spaces(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            self.assertEqual(
                connection.command(b"SET foo 0 bar baz qux"), b"OK\n"
            )
            self.assertEqual(
                connection.command(b"GET foo"), b"VALUE bar baz qux\n"
            )
        finally:
            connection.close()

    def test_keys_survive_across_connections(self):
        cache_port = self.start_cache()
        first = CacheConnection(cache_port)
        try:
            self.assertEqual(first.command(b"SET foo 0 bar"), b"OK\n")
        finally:
            first.close()
        second = CacheConnection(cache_port)
        try:
            self.assertEqual(second.command(b"GET foo"), b"VALUE bar\n")
        finally:
            second.close()

    def test_rejects_malformed_commands(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            for line in (
                b"\n",
                b"BOGUS\n",
                b"GET\n",
                b"GET foo bar\n",
                b"DELETE\n",
                b"SET\n",
                b"SET foo\n",
                b"SET foo 0\n",
                b"SET foo -1 bar\n",
                b"SET foo lots bar\n",
                b"SET foo 99999 bar\n",
                b"SET foo 0 bar\x00ignored\n",
                b"SET form\ffeed 0 bar\n",
                b"get foo\n",
            ):
                with self.subTest(line=line):
                    self.assertEqual(connection.command(line), b"ERROR\n")
        finally:
            connection.close()

    def test_rejects_oversized_key_or_value(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            long_key = b"k" * 257
            self.assertEqual(
                connection.command(b"SET " + long_key + b" 0 bar"), b"ERROR\n"
            )
            big_value = b"v" * 4097
            self.assertEqual(
                connection.command(b"SET foo 0 " + big_value), b"ERROR\n"
            )
        finally:
            connection.close()

    def test_expired_entries_free_capacity(self):
        cache_port = self.start_cache()
        connection = CacheConnection(cache_port)
        try:
            for index in range(1024):
                command = f"SET key-{index} 1 value".encode()
                self.assertEqual(connection.command(command), b"OK\n")
            self.assertEqual(connection.command(b"SET extra 0 value"), b"ERROR\n")
            time.sleep(1.2)
            self.assertEqual(
                connection.command(b"SET replacement 0 value"), b"OK\n"
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
