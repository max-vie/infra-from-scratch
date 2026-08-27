# Use Go for the DNS server

Last updated: 27.08.2026

## Summary

Implement the DNS server in Go. The HTTP component remains in Python.

## Context

The DNS component needs a long-running UDP service. Go's standard library
provides the required network primitives without an external dependency or
framework.

Python is the main language for the project and remains a suitable choice for
the HTTP component. Keeping DNS in Python would mean one language, but Go
produces a small standalone service and gives the project practice with systems
programming. CoreDNS is a useful Go DNS reference.

## Decision

Implement the DNS component in Go using its standard library. This applies
only to the DNS server. It does not change the HTTP component or require a
shared runtime.

## Consequences

The DNS server builds as a standalone program without third-party packages.
The project uses both Python and Go, so each component has its own language
tooling. If the DNS component grows, it may need a separate importable package
and executable.

## References

- [Go net package](https://pkg.go.dev/net)
- [CoreDNS](https://coredns.io/)
