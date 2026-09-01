# load-balancer

A small Python load balancer that forwards one HTTP request to one of two
configured backends in round-robin order.

## Sources

| Source | Use |
| --- | --- |
| [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html) | TCP connections, partial transfers, and connection cleanup. |
| [Python `socket` documentation](https://docs.python.org/3/library/socket.html) | Listening sockets, backend connections, and byte forwarding. |
| [Python `argparse` documentation](https://docs.python.org/3/library/argparse.html) | Listener and backend command-line options. |
| [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) | Proxy and gateway terminology. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP message syntax, framing, and connection management. |
