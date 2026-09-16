# Use passive backend health tracking

Last updated: 16.09.2026

## Summary

Track backend failures in the load balancer and temporarily skip a backend
that fails before response relay begins. Retry that backend after a fixed
one-second cooldown.

## Context

The load balancer already distributes requests between two configured backends
and fails over within the current request. A backend that remains unavailable
is still dialed again when round-robin selection reaches it.

The existing selection decision leaves health-aware backend pooling as a later
slice. Active health checks would add a scheduler, probe request semantics, and
another lifecycle to this small component.

## Decision

Keep the two required `--backend HOST:PORT` options, the shared round-robin
selection counter, and the existing request and response boundaries.

Store one retry time for each backend behind a mutex. A dial or relay failure
before response bytes reach the client marks that backend unavailable for one
second. A successful response clears its retry time. Requests skip backends
whose cooldown has not expired and return `502 Bad Gateway` when no backend is
available. A partial response keeps the existing close-without-retry behavior.

## Consequences

One failed backend no longer causes a failed connection attempt on every
round-robin turn. A recovered backend can rejoin when its cooldown expires.
The fixed cooldown can delay recovery detection by up to one second, and the
component still has no active health probes, dynamic membership, weights,
persistent connections, TLS, or request-body support.

## References

- [`load-balancer/README.md`](../../README.md)
- [`001-use-round-robin-backend-selection.md`](001-use-round-robin-backend-selection.md)
- [`002-fail-over-to-other-backend-on-connection-failure.md`](002-fail-over-to-other-backend-on-connection-failure.md)
