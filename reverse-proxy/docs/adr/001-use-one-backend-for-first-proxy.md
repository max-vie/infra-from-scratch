# Use one backend for the first reverse proxy

Last updated: 27.08.2026

## Summary

Use Python's standard library to run a local reverse proxy. It listens on
`127.0.0.1:8080` and forwards one header-terminated request per connection to
one configured backend, which defaults to `127.0.0.1:8088`.

## Context

The next network component needs to sit in front of the existing HTTP server.
A single backend demonstrates request forwarding and backend failure handling
without adding load-balancing policy at the same time.

The first HTTP implementation uses close-delimited connections and does not
handle chunked or content-encoded responses. A proxy that supports persistent
connections, request bodies, TLS, and multiple backends would need more HTTP
parsing and more failure cases than this first slice requires.

## Decision

Implement the proxy in `reverse-proxy/server.py` with Python's standard
library. Expose listener and backend host and port options through the command
line, with `127.0.0.1:8080` and `127.0.0.1:8088` as the defaults. Keep the
server callable through `serve(listen_address, backend_address)` for local
checks.

Read one request until its header terminator, with a 64 KiB limit, then
forward the raw request bytes to the backend. Relay the backend response until
the backend closes the connection. Handle one client at a time and close both
connections after each request.

Return `HTTP/1.0 400 Bad Request` for empty, incomplete, or oversized request
headers and for requests that advertise a body with `Content-Length` or
`Transfer-Encoding`. Return `HTTP/1.0 502 Bad Gateway` when the backend cannot
be reached before response relay begins. If the backend fails after response
bytes have been relayed, close the client connection without appending another
response. Do not add TLS, persistent connections, chunked transfer encoding,
request-body handling, load balancing, or DNS integration to this slice.

## Consequences

The proxy has a small, testable boundary around the existing HTTP server. The
single-backend design makes the forwarding path clear and leaves backend
selection for the later load-balancer component.

The server handles clients serially, and its first protocol boundary excludes
features that require full HTTP message framing. The integration tests cover
forwarding, malformed requests, backend failure, and partial relay behavior.

## References

- [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html)
- [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/)
