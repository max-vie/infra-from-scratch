# In-memory cache

A small C TCP cache that stores text keys and values with lazy expiry. It uses
C11, POSIX sockets, fixed bounds, and no third-party libraries.

## Protocol

One newline-terminated command per line on a persistent connection. Keys are
1–256 bytes without whitespace, values are 1–4096 bytes and may contain
spaces, TTL is `0`–`86400` seconds with `0` meaning no expiry.

| Request | Response |
| --- | --- |
| `SET <key> <ttl> <value>` | `OK`, or `ERROR` when the store is full |
| `GET <key>` | `VALUE <value>` or `NOT_FOUND` |
| `DELETE <key>` | `OK` or `NOT_FOUND` |
| malformed or oversized command | `ERROR` |
| connection above the 32-client limit | `ERROR`, then close |

The process stores up to 1024 live keys. Expired keys behave as missing and
their slots are reclaimed when needed. There is no background sweeper,
eviction, persistence, or authentication yet.

Each client connection runs in its own POSIX thread while the process-wide store
remains shared and mutex-protected. The server accepts up to 32 simultaneous
clients and releases a slot when a client disconnects. Stored keys survive
across connections.

The HTTP server can optionally use this cache for `GET /hello` through
`--cache-host` and `--cache-port`. The integration stores the body under
`http:/hello` with a 60-second TTL.

## Run

Build the cache from the project root:

```bash
gcc -std=c11 -Wall -Wextra -O2 -pthread -o in-mem-cache/server in-mem-cache/server.c
```

Start it on the default local address:

```bash
./in-mem-cache/server --listen-host 127.0.0.1 --listen-port 11211
```

## Test

```bash
python -m unittest discover -s in-mem-cache/tests -v
```

The tests compile a fresh temporary binary with strict warnings.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture decisions](docs/adr/)

## Sources

| Source | Use |
| --- | --- |
| [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) | TCP sockets, `bind`, `listen`, `accept`, partial transfers. |
| [memcached protocol](https://github.com/memcached/memcached/blob/master/doc/protocol.txt) | Text-protocol inspiration for `SET`/`GET`/`DELETE` with expiry. |
| [C `clock_gettime` documentation](https://man7.org/linux/man-pages/man2/clock_gettime.2.html) | Monotonic clock for TTL expiry. |
