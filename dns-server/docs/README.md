# Documentation

The DNS component's supporting documents live here.

## Run

Start the server from the `dns-server/` directory:

```bash
go run server.go -host 127.0.0.1 -port 8053
```

It listens on `127.0.0.1:8053` by default. Use `-host 0.0.0.0` for all
IPv4 interfaces or pass a specific local address.

Query it with:

```bash
dig @127.0.0.1 -p 8053 app.local A
```

## Tests

Run the response tests with:

```bash
go test server.go server_test.go
```

## ADRs

Architecture Decision Records live in [`adr/`](adr/).

ADR filenames use a zero-padded number and lowercase slug, for example:

```text
adr/001-short-description.md
```
