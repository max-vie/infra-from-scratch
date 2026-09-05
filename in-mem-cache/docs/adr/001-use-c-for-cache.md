# Use C for the in-memory cache

Last updated: 05.09.2026

## Summary

Implement the in-memory cache in C using only the C standard library and
POSIX sockets. It serves a minimal line-based TCP protocol with lazy TTL
expiry.

## Context

The project is mostly Python, with Go used for the DNS server to practice
systems programming. The cache is the first component where raw Linux
learning is the explicit goal and runtime behavior matters more than coding
speed, so a C implementation fits despite the heavier slice.

A Python cache would reuse the existing `unittest` subprocess patterns
directly and ship faster, while Go would give simpler concurrency than C.
Both remain options for later ports, but neither gives the manual socket and
memory practice this slice targets.

## Decision

Implement `in-mem-cache/server.c` in C11 with `-Wall -Wextra`, no third-party
dependencies. Speak a minimal text protocol over TCP: `SET <key> <ttl>
<value>`, `GET <key>`, and `DELETE <key>`, with `OK`, `VALUE`, `NOT_FOUND`,
and `ERROR` replies.

Handle one client at a time like the proxy and load balancer. Store up to
1024 keys with a 256-byte key limit and a 4096-byte value limit, enforce a
64 KiB line limit, and expire keys lazily when accessed or when their slots
are needed. Test it with Python `unittest` subprocess tests in
`in-mem-cache/tests/`, mirroring the proxy and load balancer style. Do not add
concurrency, eviction, persistence, authentication, or third-party
dependencies in this slice.

## Consequences

The cache gives raw socket and memory practice without a new test framework,
and it stays wire-compatible so any later Python, Go, or Rust port keeps the
same protocol. C brings manual buffer and lifetime risks, mitigated here by
fixed bounds, a single-threaded accept loop, and strict input rejection.

If the component grows, later slices can add concurrency, least-recently-used
or least-frequently-used eviction, persistence, or authentication, and record
each choice separately.

## References

- [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/)
- [memcached protocol](https://github.com/memcached/memcached/blob/master/doc/protocol.txt)
- [C `clock_gettime` documentation](https://man7.org/linux/man-pages/man2/clock_gettime.2.html)
