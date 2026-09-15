import socket
import sys
import threading
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(SERVER_DIR))

from application import Request
from cache_client import CacheClient, CacheError
from server import CACHE_KEY, CACHE_TTL, respond_with_cache


HOST = "127.0.0.1"


class FakeCacheServer:
    def __init__(self, reply):
        self.reply = reply
        self.received = None
        self.error = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind((HOST, 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.thread.join(timeout=1)
        self.listener.close()
        if self.thread.is_alive():
            raise AssertionError("fake cache server did not stop")
        if self.error is not None:
            raise self.error

    def _serve(self):
        try:
            with self.listener:
                connection, _ = self.listener.accept()
                with connection:
                    self.received = connection.recv(8192)
                    connection.sendall(self.reply)
        except BaseException as error:
            self.error = error


class FakeCache:
    def __init__(self, value=None, get_error=None, set_error=None):
        self.value = value
        self.get_error = get_error
        self.set_error = set_error
        self.get_calls = []
        self.set_calls = []

    def get(self, key):
        self.get_calls.append(key)
        if self.get_error:
            raise self.get_error
        return self.value

    def set(self, key, value, ttl):
        self.set_calls.append((key, value, ttl))
        if self.set_error:
            raise self.set_error


class TestCacheClient(unittest.TestCase):
    def test_get_returns_cached_value(self):
        with FakeCacheServer(b"VALUE HELLO WORLD!\n") as server:
            value = CacheClient(HOST, server.port).get(CACHE_KEY)

        self.assertEqual(value, b"HELLO WORLD!")
        self.assertEqual(server.received, b"GET http:/hello\n")

    def test_get_returns_none_for_missing_value(self):
        with FakeCacheServer(b"NOT_FOUND\n") as server:
            value = CacheClient(HOST, server.port).get(CACHE_KEY)

        self.assertIsNone(value)
        self.assertEqual(server.received, b"GET http:/hello\n")

    def test_set_sends_body_and_ttl(self):
        with FakeCacheServer(b"OK\n") as server:
            result = CacheClient(HOST, server.port).set(
                CACHE_KEY, b"HELLO WORLD!", CACHE_TTL
            )

        self.assertIsNone(result)
        self.assertEqual(
            server.received,
            b"SET http:/hello 60 HELLO WORLD!\n",
        )

    def test_rejects_unexpected_reply(self):
        with FakeCacheServer(b"BROKEN\n") as server:
            with self.assertRaises(CacheError):
                CacheClient(HOST, server.port).get(CACHE_KEY)

    def test_rejects_reply_without_newline(self):
        with FakeCacheServer(b"VALUE HELLO WORLD!") as server:
            with self.assertRaises(CacheError):
                CacheClient(HOST, server.port).get(CACHE_KEY)

    def test_rejects_non_string_key(self):
        with self.assertRaises(CacheError):
            CacheClient(HOST, 11211).get(None)


class TestCachedResponse(unittest.TestCase):
    def test_cache_hit_returns_cached_body(self):
        cache = FakeCache(value=b"CACHED")

        response = respond_with_cache(Request("GET", "/hello"), cache)

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(response.body, b"CACHED\n")
        self.assertEqual(cache.get_calls, [CACHE_KEY])
        self.assertEqual(cache.set_calls, [])

    def test_cache_miss_returns_origin_and_stores_body(self):
        cache = FakeCache()

        response = respond_with_cache(Request("GET", "/hello"), cache)

        self.assertEqual(response.body, b"HELLO WORLD!\n")
        self.assertEqual(cache.set_calls, [(CACHE_KEY, b"HELLO WORLD!", CACHE_TTL)])

    def test_cache_get_failure_returns_origin(self):
        cache = FakeCache(get_error=CacheError("unavailable"))

        response = respond_with_cache(Request("GET", "/hello"), cache)

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(response.body, b"HELLO WORLD!\n")
        self.assertEqual(cache.set_calls, [])

    def test_cache_set_failure_keeps_origin_response(self):
        cache = FakeCache(set_error=CacheError("unavailable"))

        response = respond_with_cache(Request("GET", "/hello"), cache)

        self.assertEqual(response.status, "200 OK")
        self.assertEqual(response.body, b"HELLO WORLD!\n")

    def test_other_requests_do_not_use_cache(self):
        cache = FakeCache(value=b"CACHED")

        response = respond_with_cache(Request("GET", "/health"), cache)

        self.assertEqual(response.body, b"OK\n")
        self.assertEqual(cache.get_calls, [])
        self.assertEqual(cache.set_calls, [])

    def test_non_get_hello_requests_do_not_use_cache(self):
        cache = FakeCache(value=b"CACHED")

        response = respond_with_cache(Request("POST", "/hello"), cache)

        self.assertEqual(response.status, "405 Method Not Allowed")
        self.assertEqual(cache.get_calls, [])
        self.assertEqual(cache.set_calls, [])


if __name__ == "__main__":
    unittest.main()
