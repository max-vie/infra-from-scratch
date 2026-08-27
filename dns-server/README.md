# dns-server

A small Go UDP server that resolves `app.local` to `127.0.0.1`.

## Sources

| Source | Use |
| --- | --- |
| [RFC 1034: Domain Names - Concepts and Facilities](https://www.rfc-editor.org/info/rfc1034/) | DNS concepts, domain names, and zones. |
| [RFC 1035: Domain Names - Implementation and Specification](https://www.rfc-editor.org/info/rfc1035/) | DNS message format, queries, responses, and resource records. |
| [Go `net` package](https://pkg.go.dev/net) | UDP listeners and network I/O. |
| [Go `encoding/binary` package](https://pkg.go.dev/encoding/binary) | Reading and writing DNS header fields in network byte order. |
| [CoreDNS](https://coredns.io/) | A Go-based DNS server reference. |
