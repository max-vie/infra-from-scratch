# reverse-proxy

A small Go reverse proxy that forwards one HTTP request to a configured
backend and relays the response.

## Sources

| Source | Use |
| --- | --- |
| [Go `net` documentation](https://pkg.go.dev/net) | The TCP API used to accept clients, connect to the backend, and relay bytes. |
| [Go `flag` documentation](https://pkg.go.dev/flag) | Command-line options for the listener and backend addresses. |
| [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) | Proxy and gateway terminology, response status codes, and HTTP semantics. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP message syntax, framing, and connection management. |
