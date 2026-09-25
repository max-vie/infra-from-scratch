# Use local leases for backend discovery

Last updated: 25.09.2026

## Summary

Let HTTP backends register with the load balancer through a local control
endpoint. Each registration expires unless the backend renews it.

## Context

The load balancer currently takes exactly two backend addresses at startup.
Adding or removing a server therefore requires restarting the balancer. The
existing passive health check temporarily skips failed backends, but it does
not change membership.

A separate registry process would add another service and failure boundary.
Reloading a shared configuration file would make backend processes coordinate
file writes. A control endpoint in the balancer keeps membership beside the
selection and health state it changes.

## Decision

Keep the existing two-backend command line mode. When `-registry-port PORT` is
set, start with no backends, reject `-backend` options, and expose
`GET`, `PUT`, and `DELETE /backends` on `127.0.0.1:PORT`. `PUT` and `DELETE` use a
plain IPv4 `HOST:PORT` request body. Limit request bodies to 128 bytes and
membership to 32 addresses. `GET` returns one address per line.

`PUT` adds an address or renews its three-second lease; `DELETE` removes it.
The HTTP server's optional `--registry-port` flag sends `PUT` every second.
Graceful shutdown sends `DELETE`; after an abrupt exit, the lease expires.
Registration failures are retried while the HTTP server continues serving.
The HTTP server reports a registration failure once until a later renewal
succeeds. Registry mode requires a numeric IPv4 listen host on the HTTP server.

The balancer takes a membership snapshot for each valid request. It keeps the
current round-robin, one-second health cooldown, failover, and partial-response
rules within that snapshot. An empty or unavailable pool returns `502 Bad
Gateway`. No remote registry, authentication, persistent membership, or active
health probes are introduced.

## Consequences

Backends can join and leave without restarting the balancer. Existing static
command lines continue to work. Backends retry registration until the local
control port becomes available. A crashed backend can remain listed for up to
three seconds, and a request already in progress may finish against a removed
backend.

The balancer owns membership and leases in `load-balancer/server.go`; the HTTP
server renews its own address in `http-server/server.py`. Component tests cover
registration, duplicate renewal, removal, invalid input, and static routing.
The integration suite proves that a backend stays registered beyond one lease,
expires after termination, and can be replaced without interrupting the DNS
and reverse proxy path.

## References

- [`load-balancer/docs/adr/004-use-passive-backend-health.md`](../../load-balancer/docs/adr/004-use-passive-backend-health.md)
- [`load-balancer/README.md`](../../load-balancer/README.md)
- [`http-server/README.md`](../../http-server/README.md)
