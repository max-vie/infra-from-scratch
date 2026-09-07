# HTTP client and server

A small Python implementation of URL parsing, HTTP requests, HTTP transport,
and application routing. It uses the standard library and sends protocol bytes
over TCP sockets.

## Behavior

`URL(address).request()` sends a `GET` request and returns a `Response` with the
HTTP version, numeric status, reason phrase, case-insensitive headers, and raw
body bytes. Well-formed error responses are returned like successful responses.

The server reads one request through `\r\n\r\n`, limits the header block to 64
KiB, and closes the connection after responding.

| Request | Response |
| --- | --- |
| `GET /` | `200 OK` and `HELLO WORLD!` |
| `GET /health` | `200 OK` and `OK` |
| `GET /hello` | `200 OK` and `HELLO WORLD!` |
| unknown GET route | `404 Not Found` |
| non-GET method | `405 Method Not Allowed` |
| malformed, incomplete, oversized, or body-framed request | `400 Bad Request` |

The client and server do not implement HTTPS, request bodies, persistent
connections, chunked transfer encoding, or content encoding.

## Run

Start the server from the project root:

```bash
python http-server/server.py --host 127.0.0.1 --port 8088
```

In another terminal, send a request with the custom client:

```bash
python http-server/client.py http://127.0.0.1:8088/health
```

The server defaults to `0.0.0.0:8088`, which binds all IPv4 interfaces. Pass a
specific local address with `--host` when the server should remain local.

## Test

```bash
python -m unittest discover -s http-server/tests -v
python -m py_compile http-server/server.py http-server/client.py
```

## Documentation

- [Documentation index](docs/README.md)
- [HTTP version boundaries](docs/http-versions.md)
- [Architecture decisions](docs/adr/)

## Sources

| Source | Use |
| --- | --- |
| [Web Browser Engineering](https://browser.engineering/) | URL parsing, page loading, and browser-side HTTP requests. |
| [Let's Build A Web Server, Part 1](https://ruslanspivak.com/lsbaws-part1/) | Build a minimal server from socket setup through request and response handling. |
| [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html) | Python socket operations, including `bind`, `listen`, `accept`, `send`, `recv`, partial transfers, and connection cleanup. |
| [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/info/rfc9112/) | HTTP/1.1 message syntax, parsing, framing, and connection management. It does not cover TLS. |
| [Interesting video by Low Level](https://www.youtube.com/watch?v=ySQQ5IKTO1c) | Security research and vulnerability discovery. |
