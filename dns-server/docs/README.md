# Documentation

This directory stores documentation for the DNS server project.

## Run

Start the server from the `dns-server/` directory:

```bash
go run server.go
```

It listens on `127.0.0.1:8053` and resolves `app.local` to `127.0.0.1`.

Query it with:

```bash
dig @127.0.0.1 -p 8053 app.local A
```

## Test

Run the response tests with:

```bash
go test server.go server_test.go
```

## Structure

- [`adr/`](adr/) contains Architecture Decision Records.

ADRs use a sequential number and short description, for example:

```text
adr/0001-short-description.md
```
