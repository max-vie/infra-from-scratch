# Use round-robin selection for the first load balancer

Last updated: 01.09.2026

## Summary

Use deterministic round-robin selection between two configured backends. The
load balancer uses Python's standard library and handles one request per
connection.

## Context

The reverse proxy has one backend. The next network step needs backend
selection, but it does not need health tracking or retry policy yet. Two fixed
backends and deterministic selection show how requests are distributed with a
small amount of state.

## Decision

Implement `load-balancer/server.py` with two required `--backend HOST:PORT`
options and a default listener at `127.0.0.1:8000`. After local validation, each
request selects the next backend in order and forwards the header-terminated
request. The load balancer relays the response until the backend closes the
connection.

Keep the existing protocol boundary: reject empty, incomplete, oversized, or
body-framed requests with `400 Bad Request`. Return `502 Bad Gateway` when the
selected backend fails before response relay begins. If response bytes have
already reached the client, close the connection without appending another
error. Do not retry requests or remove failed backends.

## Consequences

Valid requests alternate between the two backends. A failed backend affects
the request assigned to it, while the next valid request moves to the other
backend. The server remains serial and does not support health checks, weights,
persistent connections, TLS, or request bodies.

If the component grows, a later slice can replace round-robin selection with a
health-aware backend pool and record the new failure policy separately.

## References

- [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/)
- [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/)
