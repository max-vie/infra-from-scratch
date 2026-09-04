# http-server

A small Python implementation of URL parsing, HTTP requests, and a basic
HTTP server.

## HTTP client

`URL(address).request()` sends a `GET` request and returns a `Response` value
with the HTTP version, numeric status, reason phrase, case-insensitive headers,
and the raw response body as bytes. Well-formed error responses are returned
like successful responses.

The client reads supported responses until the connection closes. It raises
`NotImplementedError` for `Transfer-Encoding` and `Content-Encoding`; chunked
responses and persistent connections are not implemented.

## HTTP server MVP

The server listens on port `8088`, reads one request through `\r\n\r\n`, and
closes the connection after responding. It accepts HTTP/1.0 and HTTP/1.1
request lines and limits the header block to 64 KiB.

Run it with an explicit listener address when needed:

```bash
python http-server/server.py --host 127.0.0.1 --port 8088
```

The default host is `0.0.0.0`, which binds all IPv4 interfaces. Use a
specific local address or `0.0.0.0` with `--host`.

| Request | Response |
| --- | --- |
| `GET /` | `200 OK` and `HELLO WORLD!` |
| `GET /health` | `200 OK` and `OK` |
| `GET /hello` | `200 OK` and `HELLO WORLD!` |
| unknown GET route | `404 Not Found` |
| non-GET method | `405 Method Not Allowed` |
| malformed, incomplete, oversized, or body-framed request | `400 Bad Request` |

Request bodies, persistent connections, and chunked transfer encoding are not
implemented yet.

## Sources

| Source | Use |
| --- | --- |
| [Web Browser Engineering](https://browser.engineering/) | URL parsing, page loading, and browser-side HTTP requests. |
| [Let's Build A Web Server, Part 1](https://ruslanspivak.com/lsbaws-part1/) | Build a minimal server from socket setup through request and response handling. |
| [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html) | Python socket operations, including `bind`, `listen`, `accept`, `send`, `recv`, partial transfers, and connection cleanup. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP/1.1 message syntax, parsing, framing, and connection management. It does not cover TLS. |
| [Interesting video by Low Level](https://www.youtube.com/watch?v=ySQQ5IKTO1c) | Security research and vulnerability discovery. |
