# Keep tests with the Go package for the MVP

Last updated: 27.08.2026

## Summary

Keep `server_test.go` beside `server.go` while the DNS component remains an
MVP. The tests can exercise private response-building functions without adding
a package or executable layout yet.

## Context

The DNS tests call the private `makeResponse` function to check response
construction directly. Keeping the test file beside the implementation lets
both files use the same `main` package and keeps the tests close to the code.

A separate importable package and `cmd/` executable would suit a larger
component, but they would add structure and interfaces to this small one.

## Decision

Keep `server_test.go` beside `server.go` in the `dns-server/` directory. Keep
the current package layout for the MVP. If the component grows, move it to an
importable package with a separate executable and test directory.

## Consequences

The tests can verify private response-building behavior without a public
package interface. The executable and tests remain coupled to the current
layout. A future restructure must update the package boundary and test imports
together.

## References

- [Go testing package](https://pkg.go.dev/testing)
