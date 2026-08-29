# reverse-proxy

A small Python reverse proxy that forwards one HTTP request to a configured
backend and relays the response.

## Sources

| Source | Use |
| --- | --- |
| [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html) | TCP connections, partial transfers, and connection cleanup. |
| [Python `socket` documentation](https://docs.python.org/3/library/socket.html) | The socket API used to accept clients, connect to the backend, and relay bytes. |
| [Python `argparse` documentation](https://docs.python.org/3/library/argparse.html) | Command-line options for the listener and backend addresses. |
| [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/info/rfc9110/) | Proxy and gateway terminology, response status codes, and HTTP semantics. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP message syntax, framing, and connection management. |
