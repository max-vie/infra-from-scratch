# Documentation

The load balancer documentation lives here.

## Run

Start two HTTP servers from the project root:

```bash
python http-server/server.py --host 127.0.0.1 --port 8088
python http-server/server.py --host 127.0.0.1 --port 8089
```

Start the load balancer in another terminal:

```bash
python load-balancer/server.py \
  --listen-host 127.0.0.1 \
  --listen-port 8000 \
  --backend 127.0.0.1:8088 \
  --backend 127.0.0.1:8089
```

It sends successive valid requests to the two backends in alternating order.
When the selected backend cannot be reached before response bytes start, it
tries the other backend once in the same client connection. It returns `502
Bad Gateway` only when both backends fail. It does not remove backends from
the list or run health checks.

## Test

Run the load balancer tests from the project root:

```bash
python -m unittest discover -s load-balancer/tests -v
python -m py_compile load-balancer/server.py
```

## ADRs

Architecture Decision Records live in [`adr/`](adr/).

ADR filenames use a zero-padded number and lowercase slug, for example:

```text
adr/001-short-description.md
```
