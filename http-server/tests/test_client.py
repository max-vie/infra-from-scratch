import sys
from pathlib import Path
import unittest

# Add the parent directory so the test can import client.py directly.
sys.path.insert(0, str(Path(__file__).parents[1]))

from client import URL


class TestURL(unittest.TestCase):
    # Verify that a host, port, and path are parsed correctly.
    def test_parses_url(self):
        url = URL("localhost:8088/hello")

        self.assertEqual(url.host, "localhost")
        self.assertEqual(url.port, 8088)
        self.assertEqual(url.path, "/hello")


if __name__ == "__main__":
    unittest.main()
