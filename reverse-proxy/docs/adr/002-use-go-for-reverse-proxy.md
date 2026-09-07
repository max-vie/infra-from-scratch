# Use Go for the reverse proxy

Last updated: 07.09.2026

## Summary

Rewrite the reverse proxy in Go, replacing the Python implementation. The
project's language mapping assigns Go to network infrastructure components.

## Context

This decision replaces the Python implementation choice in
[`001-use-one-backend-for-first-proxy.md`](001-use-one-backend-for-first-proxy.md).
That record continues to define the single-backend and protocol boundaries.

The project maps each component to a language: Go for network infrastructure,
C for systems components, and Python for HTTP fundamentals. The reverse proxy
was first built in Python, but the mapping assigns it to Go alongside the DNS
server, load balancer, and later components.

The existing behavior does not change. ADR 001 defines the protocol boundary:
one backend, one header-terminated request per connection, a 64 KiB header
limit, `400 Bad Request` for malformed or body-framed requests, and
`502 Bad Gateway` when the backend fails before response relay begins.

The tests are black-box: they start the server as a subprocess and exchange
bytes over TCP. The Go rewrite passes them without changing any assertion.

## Decision

Implement the proxy in `reverse-proxy/server.go` with Go's standard library,
following the DNS server precedent in `dns-server/docs/adr/001`. Command-line
options keep their names and switch to Go `flag` syntax, for example
`-listen-host`. Delete `reverse-proxy/server.py`.

## Consequences

The proxy builds as a standalone program without third-party packages, like
the DNS server. Tests run the server with `go run server.go`, matching the DNS
component. The project standardizes network components on Go, and the Python
codebase shrinks to the HTTP server and client plus test harnesses.

## References

- [Go net package](https://pkg.go.dev/net)
- [Go flag package](https://pkg.go.dev/flag)
