# Load balancer

A small Go load balancer that handles clients concurrently and sends HTTP
requests to registered or configured backends in round-robin order.

## Behavior

The load balancer validates one header-terminated request before selecting a
backend. It handles each client in its own goroutine, so a slow or incomplete
request does not block other clients. Successive valid requests use the
available backends in round-robin order. A backend that fails before response
bytes reach the client is skipped for one second, then tried again. The
balancer tries another backend when needed and returns `502 Bad Gateway` when
no backend can serve the request.

Without `-registry-port`, exactly two `-backend HOST:PORT` options are required.
With `-registry-port`, the balancer starts empty and listens for registration
requests on `127.0.0.1` at that port. `PUT /backends` registers or renews a
backend, `DELETE /backends` removes it, and `GET /backends` lists current
addresses. `PUT` and `DELETE` take a plain IPv4 `HOST:PORT` request body.
Successful updates return `204 No Content`; invalid addresses return `400 Bad
Request`. Removing an unknown address returns `404 Not Found`; registering above
the 32-backend limit returns `409 Conflict`.
Registrations expire after three seconds without renewal. The registry holds up
to 32 backends and is not persisted. New requests use the current membership;
requests already in progress may finish against a backend being removed.

The balancer does not run active health checks, use weights, terminate TLS, or
support request bodies and persistent connections.

## Run

Start two HTTP backends from the project root in separate terminals:

```bash
python http-server/server.py --host 127.0.0.1 --port 8088
python http-server/server.py --host 127.0.0.1 --port 8089
```

Start the load balancer in another terminal:

```bash
(cd load-balancer && go run server.go \
  -listen-host 127.0.0.1 \
  -listen-port 8000 \
  -backend 127.0.0.1:8088 \
  -backend 127.0.0.1:8089)
```

Requests to `http://127.0.0.1:8000` now alternate between the backends.

For local discovery, start the balancer without `-backend` options:

```bash
(cd load-balancer && go run server.go -listen-port 8000 -registry-port 8001)
```

Then start HTTP backends with `--registry-port 8001` and explicit local ports.
They renew their registrations every second. A terminated backend disappears
after its lease expires:

```bash
python http-server/server.py --host 127.0.0.1 --port 8088 --registry-port 8001
python http-server/server.py --host 127.0.0.1 --port 8089 --registry-port 8001
```

The registry endpoint also accepts direct local updates:

```bash
curl -X DELETE --data-binary '127.0.0.1:8088' http://127.0.0.1:8001/backends
```

## Test

```bash
python -m unittest discover -s load-balancer/tests -v
```

## Documentation

- [Documentation index](docs/README.md)
- [Architecture decisions](docs/adr/)

## Sources

| Source | Use |
| --- | --- |
| [Go `net` documentation](https://pkg.go.dev/net) | The TCP API used for listening sockets, backend connections, and byte forwarding. |
| [Go `flag` documentation](https://pkg.go.dev/flag) | Listener and backend command-line options. |
| [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) | Proxy and gateway terminology. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP message syntax, framing, and connection management. |
