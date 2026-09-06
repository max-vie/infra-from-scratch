# Documentation

The reverse-proxy documentation lives here.

## Run

Start the HTTP backend from the project root:

```bash
python http-server/server.py
```

In another terminal, start the reverse proxy:

```bash
go run server.go
```

from `reverse-proxy/`. The proxy listens on `127.0.0.1:8080` and forwards to
`127.0.0.1:8088` by default. Use `-help` to see the listener and backend
options.

## Test

Run the reverse proxy tests from the project root:

```bash
python -m unittest discover -s reverse-proxy/tests -v
```

The forwarding path should return the backend response. An unavailable
backend should return `502 Bad Gateway`.

## ADRs

Architecture Decision Records live in [`adr/`](adr/).

ADR filenames use a zero-padded number and lowercase slug, for example:

```text
adr/001-short-description.md
```
