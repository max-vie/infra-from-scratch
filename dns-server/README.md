# DNS server

A small Go UDP server that parses DNS messages and resolves `app.local` to
`127.0.0.1` using only the standard library.

## Behavior

The server accepts one-question DNS queries over IPv4 UDP. It returns a fixed A
record for `app.local`, returns `NXDOMAIN` for unknown names, and ignores
malformed messages it cannot parse.

It does not perform recursive resolution, caching, zone loading, or DNS over
TCP.

## Run

Start the server from the project root:

```bash
(cd dns-server && go run server.go -host 127.0.0.1 -port 8053)
```

Query the local record with `dig`:

```bash
dig @127.0.0.1 -p 8053 app.local A
```

## Test

```bash
(cd dns-server && go test server.go server_test.go)
```

## Documentation

- [Documentation index](docs/README.md)
- [Architecture decisions](docs/adr/)

## Sources

| Source | Use |
| --- | --- |
| [RFC 1034: Domain Names - Concepts and Facilities](https://www.rfc-editor.org/info/rfc1034/) | DNS concepts, domain names, and zones. |
| [RFC 1035: Domain Names - Implementation and Specification](https://www.rfc-editor.org/info/rfc1035/) | DNS message format, queries, responses, and resource records. |
| [Go `net` package](https://pkg.go.dev/net) | UDP listeners and network I/O. |
| [Go `encoding/binary` package](https://pkg.go.dev/encoding/binary) | Reading and writing DNS header fields in network byte order. |
| [CoreDNS](https://coredns.io/) | A Go-based DNS server reference. |
