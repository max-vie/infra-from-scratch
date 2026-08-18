import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path


# Add the parent directory so the test can import client.py directly.
sys.path.insert(0, str(Path(__file__).parents[1]))

from client import URL


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
            body = URL("localhost:8088/").request()
            self.assertEqual(body, "HELLO WORLD!\n")
        finally:
            # Always stop the server after the test.
            server.terminate()
            server.wait()

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
