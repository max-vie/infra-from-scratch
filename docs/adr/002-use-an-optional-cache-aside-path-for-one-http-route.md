# Use an optional cache-aside path for one HTTP route

Last updated: 15.09.2026

## Summary

Connect the existing C cache to the HTTP server as an optional cache-aside
adapter for `GET /hello`. The cache stores only the route body, while the HTTP
server keeps ownership of status, headers, and response framing.

## Context

The DNS, reverse proxy, load balancer, and HTTP server already run together in
the integration suite. The cache has its own tested TCP protocol but is not yet
part of that request path.

A generic response envelope would add serialization and validation rules. A
cache required for every HTTP request would change the current default runtime.
Caching every route would add route and invalidation policy before the first
integration has a clear use case.

## Decision

Add a small Python standard-library `CacheClient` that opens one TCP connection
per command, uses a 0.5-second timeout, and accepts only the existing `GET` and
`SET` replies. Connection, timeout, malformed-reply, and unexpected-reply
errors raise `CacheError`.

Enable the adapter only when the HTTP server receives `--cache-host`; use
`--cache-port 11211` by default. For `GET /hello`, use the key `http:/hello`,
store `HELLO WORLD!` with a 60-second TTL, and restore the response's terminal
newline on a cache hit.

Keep `application.respond()` pure. A cache hit returns a successful `/hello`
response, a miss calls the existing application and attempts `SET`, and any
cache failure serves the application response without retrying or returning a
cache-specific error. The integration suite starts the existing C cache and
passes its address to both HTTP backends.

## Consequences

The complete tested path now exercises the C cache while the HTTP server still
works unchanged when cache flags are absent. Both HTTP backends share cached
values through the same cache process. Cache failures do not reduce HTTP
availability, but this slice adds no cache health tracking, metrics, or
logging policy.

The cache remains a line-based TCP store with its existing bounds, lazy expiry,
and standalone tests. Persistence, eviction, authentication, full-response
serialization, and caching additional routes remain follow-up decisions.

## References

- [`http-server/README.md`](../../http-server/README.md)
- [`in-mem-cache/README.md`](../../in-mem-cache/README.md)
- [`http-server/docs/adr/002-separate-application-routing-from-transport.md`](../../http-server/docs/adr/002-separate-application-routing-from-transport.md)
- [`in-mem-cache/docs/adr/002-handle-concurrent-clients.md`](../../in-mem-cache/docs/adr/002-handle-concurrent-clients.md)
