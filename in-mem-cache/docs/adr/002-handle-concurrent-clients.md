# Handle cache clients concurrently

Last updated: 13.09.2026

## Summary

Handle each accepted cache connection in its own detached POSIX thread while
protecting the shared in-memory store with one mutex.

## Context

[`001-use-c-for-cache.md`](001-use-c-for-cache.md) records the original
single-client MVP decision and its protocol, storage, and expiry rationale.
The cache previously handled a client until disconnect before accepting the
next one, so an incomplete command prevented other clients from making
progress. The existing text protocol already supports persistent connections,
and the store is process-wide.

A thread-per-connection implementation uses the POSIX facilities already
needed by the C server. A process-per-client design would give each process a
separate store, while a worker pool would add scheduling and capacity policy to
this focused change.

## Decision

Create one detached `pthread` for each accepted client socket. Transfer socket
ownership to the thread through allocated storage, keep receive buffers local to
the client handler, and close the socket when the handler returns. Close the
socket and continue accepting when thread setup fails.

Protect lookup, expiry reclamation, insertion, overwrite, and deletion with one
process-wide mutex. Copy a `GET` value while holding the mutex, then release it
before writing the response. Parse commands and send responses outside the
mutex when they do not access the store.

Keep the existing `SET`, `GET`, and `DELETE` wire format, persistent connection
behavior, bounds, lazy expiry, and command responses. Build the server and its
tests with `-pthread`. Do not add pooling, connection limits, timeouts,
eviction, persistence, authentication, or cache integration.

## Consequences

An incomplete or slow client no longer blocks connections accepted afterward.
Store operations are serialized by one simple mutex, which keeps the current
fixed-array implementation intact and provides a clear throughput ceiling for
future work. Idle clients still occupy detached threads until they disconnect.

The black-box suite covers concurrent progress, independent concurrent values,
and the existing protocol, TTL, capacity, and cross-connection behavior.

## References

- [POSIX `pthread_create`](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_create.html)
- [C `pthread_mutex_lock`](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_mutex_lock.html)
- [`001-use-c-for-cache.md`](001-use-c-for-cache.md)
