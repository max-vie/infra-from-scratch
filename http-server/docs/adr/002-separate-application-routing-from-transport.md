# Separate application routing from HTTP transport

Last updated: 2026-09-02

## Summary

Keep socket handling in `server.py` and expose HTTP application behavior through
the pure `application.respond()` interface. The interface uses `Request` and
`Response` values and does not create a new process or network service.

## Context

The HTTP server handled request parsing, socket I/O, response serialization, and
route selection in one module. That made route behavior depend on a live socket
even though the current application only needs a method and target.

Moving the entire parser would add a second protocol interface before the server
needs one. Keeping routing inline would leave application behavior coupled to
transport tests.

## Decision

Define `Request` with `method` and `target` fields, and `Response` with `status`,
`body`, and response `headers` in `http-server/application.py`. The pure
`respond(request)` function returns the current route result without socket or
HTTP framing work.

Keep request parsing, body rejection, response serialization, listener setup,
and connection cleanup in `server.py`. The transport adapter constructs a
`Request`, calls `respond()`, and serializes the returned `Response`.

Preserve the existing wire behavior, supported routes, status lines, headers,
body bytes, and close-delimited connections. Test application behavior through
`respond()` and retain socket tests for transport behavior.

## Consequences

Route behavior can be tested without starting a server, while the transport
tests continue to cover the actual HTTP path. Changes to routing stay local to
the application module; changes to framing stay local to the transport
adapter.

The application interface currently excludes request headers because no route
uses them. A future feature that needs headers can extend the interface with a
separate decision.

## References

- [`http-versions.md`](../http-versions.md)
- [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/)
