# HTTP versions

`URL.request()` sends `HTTP/1.0` requests. The server sends `HTTP/1.1`
responses. The server smoke test sends an `HTTP/1.1` request.

HTTP/1.0 and HTTP/1.1 interoperate for the features used here. The response
uses `Content-Length` and `Connection: close`, so the HTTP/1.0 request can read
it. Persistent connections and chunked transfer encoding need separate
handling. `URL.request()` raises `NotImplementedError` for responses that
include `Transfer-Encoding` or `Content-Encoding`.

The first reverse-proxy version should use HTTP/1.0 requests, close each
connection, and avoid chunked transfer encoding and persistent connections.
