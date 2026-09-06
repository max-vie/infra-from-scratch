# load-balancer

A small Go load balancer that forwards one HTTP request to one of two
configured backends in round-robin order.

## Sources

| Source | Use |
| --- | --- |
| [Go `net` documentation](https://pkg.go.dev/net) | The TCP API used for listening sockets, backend connections, and byte forwarding. |
| [Go `flag` documentation](https://pkg.go.dev/flag) | Listener and backend command-line options. |
| [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) | Proxy and gateway terminology. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP message syntax, framing, and connection management. |
