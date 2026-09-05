# Fail over to the other backend on connection failure

Last updated: 05.09.2026

## Summary

Try the other configured backend once when the selected backend fails before
response bytes reach the client. Return `502 Bad Gateway` only when both
backends fail.

## Context

The first load balancer used deterministic round-robin between two backends
and returned `502 Bad Gateway` for the request assigned to a dead backend. The
next request moved to the other backend, so one dead backend caused every
other request to fail visibly even though a healthy backend existed.

The component still needs no health tracking, backend removal, weights, or
retry policy beyond one failover per request.

## Decision

Keep two required `--backend HOST:PORT` options and the existing protocol
boundary: reject empty, incomplete, oversized, or body-framed requests with
`400 Bad Request` before backend selection.

For each valid request, try the round-robin selected backend first. On
`OSError` before any response bytes are relayed, try the other backend once in
the same client connection. Send `502 Bad Gateway` only when both attempts
fail before response start. If response bytes already reached the client,
close the connection without appending another error and do not retry.

Advance the round-robin pointer by one from the originally selected backend
regardless of which backend served the request, preserving alternation when
both backends are healthy.

## Consequences

One dead backend no longer causes user-visible `502` responses while the other
backend is healthy; the failed attempt costs one extra backend connection per
request. Both backends down still returns `502`. Partial responses keep the
existing behavior of closing without a second error. The server remains serial
with no health checks, weights, persistent connections, TLS, or request
bodies.

## References

- [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/)
- [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/)
