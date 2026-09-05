# in-mem-cache

A small C TCP cache that stores text keys and values with lazy TTL expiry.

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

The process stores up to 1024 live keys. Expired keys behave as missing and
their slots are reclaimed when needed. There is no background sweeper,
eviction, persistence, or authentication yet.

## Sources

| Source | Use |
| --- | --- |
| [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) | TCP sockets, `bind`, `listen`, `accept`, partial transfers. |
| [memcached protocol](https://github.com/memcached/memcached/blob/master/doc/protocol.txt) | Text-protocol inspiration for `SET`/`GET`/`DELETE` with expiry. |
| [C `clock_gettime` documentation](https://man7.org/linux/man-pages/man2/clock_gettime.2.html) | Monotonic clock for TTL expiry. |
