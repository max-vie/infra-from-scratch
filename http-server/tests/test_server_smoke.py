import socket
import subprocess
import sys
import time
import unittest


class TestServer(unittest.TestCase):
    def test_returns_hello_world(self):
        # Start the server.
        server = subprocess.Popen(
            [sys.executable, "http-server/server.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            time.sleep(0.2)

            # Send one request.
            with socket.create_connection(("127.0.0.1", 8088)) as connection:
                connection.sendall(
                    b"GET / HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"\r\n"
                )
                response = connection.recv(1024)

            # Check the response.
            self.assertIn(b"HTTP/1.1 200 OK", response)
            self.assertIn(b"HELLO WORLD!", response)

        finally:
            # Stop the server.
            server.terminate()
            server.wait()


if __name__ == "__main__":
    unittest.main()
