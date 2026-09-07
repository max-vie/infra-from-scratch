# Use Go for the load balancer

Last updated: 07.09.2026

## Summary

Rewrite the load balancer in Go, replacing the Python implementation. The
project's language mapping assigns Go to network infrastructure components.

## Context

This decision replaces the Python implementation choices in
[`001-use-round-robin-backend-selection.md`](001-use-round-robin-backend-selection.md)
and
[`002-fail-over-to-other-backend-on-connection-failure.md`](002-fail-over-to-other-backend-on-connection-failure.md).
Their backend-selection and failover policies remain in force.

The project maps each component to a language: Go for network infrastructure,
C for systems components, and Python for HTTP fundamentals. The load balancer
was first built in Python, but the mapping assigns it to Go alongside the DNS
server, reverse proxy, and later components.

The existing behavior does not change. ADR 001 defines round-robin selection
between two backends; ADR 002 defines failover to the other backend when the
selected one fails before response bytes reach the client. Both decisions
remain in force.

The tests are black-box with one exception: the invalid-configuration cases
called `parse_args` in-process. Those cases now validate the command-line
interface by running the Go program as a subprocess, matching the rest of the
test style.

## Decision

Implement the load balancer in `load-balancer/server.go` with Go's standard
library, following the DNS server precedent in `dns-server/docs/adr/001`.
Command-line options keep their names and switch to Go `flag` syntax, for
example `-backend`. Delete `load-balancer/server.py`.

## Consequences

The load balancer builds as a standalone program without third-party
packages, like the DNS server. Tests run the server with `go run server.go`,
matching the other Go components. All argument validation is exercised through
the process boundary, so the test suite no longer depends on the
implementation language of the server.

## References

- [Go net package](https://pkg.go.dev/net)
- [Go flag package](https://pkg.go.dev/flag)
