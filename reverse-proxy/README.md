# Reverse proxy

A small Go reverse proxy that handles clients concurrently and forwards one
HTTP request per connection to a configured backend.

## Behavior

The proxy reads one header-terminated request, forwards the raw bytes, and
relays the response until the backend closes its connection. It limits request
headers to 64 KiB and returns `400 Bad Request` for empty, incomplete,
oversized, or body-framed requests. It returns `502 Bad Gateway` for non-timeout
backend failures before response bytes reach the client and `504 Gateway
Timeout` when the backend does not respond before the five-second deadline.

The proxy does not terminate TLS or support request bodies, persistent
connections, chunked transfer encoding, or multiple backends.

## Run

Start the HTTP backend from the project root:

```bash
python http-server/server.py --host 127.0.0.1 --port 8088
```

In another terminal, start the reverse proxy:

```bash
(cd reverse-proxy && go run server.go \
  -listen-host 127.0.0.1 \
  -listen-port 8080 \
  -backend-host 127.0.0.1 \
  -backend-port 8088)
```

Requests to `http://127.0.0.1:8080` now pass through the proxy.

## Test

```bash
python -m unittest discover -s reverse-proxy/tests -v
```

## Documentation

- [Documentation index](docs/README.md)
- [Architecture decisions](docs/adr/)

## Sources

| Source | Use |
| --- | --- |
| [Go `net` documentation](https://pkg.go.dev/net) | The TCP API used to accept clients, connect to the backend, and relay bytes. |
| [Go `flag` documentation](https://pkg.go.dev/flag) | Command-line options for the listener and backend addresses. |
| [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) | Proxy and gateway terminology, response status codes, and HTTP semantics. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP message syntax, framing, and connection management. |
