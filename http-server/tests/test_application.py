import sys
import unittest
from pathlib import Path


# Add the parent directory so the test can import application.py directly.
sys.path.insert(0, str(Path(__file__).parents[1]))

from application import Request, respond


class TestApplication(unittest.TestCase):
    def test_responds_to_known_routes(self):
        for target in ("/", "/hello"):
            with self.subTest(target=target):
                response = respond(Request("GET", target))

                self.assertEqual(response.status, "200 OK")
                self.assertEqual(response.body, b"HELLO WORLD!\n")
                self.assertEqual(response.headers, ())

    def test_responds_to_health_route(self):
        response = respond(Request("GET", "/health"))

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(response.body, b"OK\n")
        self.assertEqual(response.headers, ())

    def test_returns_not_found_for_unknown_route(self):
        response = respond(Request("GET", "/missing"))

        self.assertEqual(response.status, "404 Not Found")
        self.assertEqual(response.body, b"Not Found\n")
        self.assertEqual(response.headers, ())

    def test_returns_method_not_allowed_for_non_get(self):
        response = respond(Request("POST", "/hello"))

        self.assertEqual(response.status, "405 Method Not Allowed")
        self.assertEqual(response.body, b"Method Not Allowed\n")
        self.assertEqual(response.headers, (("Allow", "GET"),))


if __name__ == "__main__":
    unittest.main()
