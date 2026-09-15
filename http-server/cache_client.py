import socket


DEFAULT_TIMEOUT = 0.5
KEY_MAX = 256
VALUE_MAX = 4096
TTL_MAX = 86400
MAX_REPLY_SIZE = VALUE_MAX + len(b"VALUE ") + 1


class CacheError(Exception):
    """The cache could not complete or validate a command."""


def _encode_key(key):
    if not isinstance(key, str):
        raise CacheError("cache keys must be strings")
    try:
        encoded = key.encode("ascii")
    except UnicodeEncodeError as error:
        raise CacheError("cache keys must use ASCII") from error
    if not 0 < len(encoded) <= KEY_MAX or any(byte <= 32 for byte in encoded):
        raise CacheError("invalid cache key")
    return encoded


def _encode_value(value):
    if not isinstance(value, bytes) or not 0 < len(value) <= VALUE_MAX:
        raise CacheError("invalid cache value")
    if b"\r" in value or b"\n" in value or b"\x00" in value:
        raise CacheError("invalid cache value")
    return value


class CacheClient:
    def __init__(self, host, port, timeout=DEFAULT_TIMEOUT):
        self.address = (host, port)
        self.timeout = timeout

    def _command(self, command):
        try:
            with socket.create_connection(self.address, timeout=self.timeout) as connection:
                connection.sendall(command)
                with connection.makefile("rb") as response:
                    reply = response.readline(MAX_REPLY_SIZE + 1)
        except OSError as error:
            raise CacheError("cache request failed") from error

        if len(reply) > MAX_REPLY_SIZE or not reply.endswith(b"\n"):
            raise CacheError("malformed cache reply")
        return reply

    def get(self, key):
        key = _encode_key(key)
        reply = self._command(b"GET " + key + b"\n")
        if reply == b"NOT_FOUND\n":
            return None
        if reply.startswith(b"VALUE ") and reply.count(b"\n") == 1:
            value = reply[len(b"VALUE ") : -1]
            return _encode_value(value)
        raise CacheError("unexpected cache GET reply")

    def set(self, key, value, ttl):
        key = _encode_key(key)
        value = _encode_value(value)
        if not isinstance(ttl, int) or not 0 <= ttl <= TTL_MAX:
            raise CacheError("invalid cache TTL")
        reply = self._command(
            b"SET " + key + b" " + str(ttl).encode("ascii") + b" " + value + b"\n"
        )
        if reply != b"OK\n":
            raise CacheError("unexpected cache SET reply")
