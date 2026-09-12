# Load balancer

A small Go load balancer that handles clients concurrently and sends HTTP
requests to two fixed backends in round-robin order.

## Behavior

The load balancer validates one header-terminated request before selecting a
backend. It handles each client in its own goroutine, so a slow or incomplete
request does not block other clients. Successive valid requests alternate
between the two backends. If the selected backend cannot connect before
response bytes reach the client, the balancer tries the other backend once. It
returns `502 Bad Gateway` only when both backends fail.

It does not run health checks, remove failed backends, use weights, terminate
TLS, or support request bodies and persistent connections.

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
