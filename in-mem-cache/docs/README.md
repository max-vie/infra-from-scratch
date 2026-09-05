# Documentation

The in-memory cache documentation lives here.

## Run

Build the cache from the project root:

```bash
gcc -std=c11 -Wall -Wextra -O2 -o in-mem-cache/server in-mem-cache/server.c
```

Start the cache in another terminal:

```bash
./in-mem-cache/server --listen-host 127.0.0.1 --listen-port 11211
```

It handles one client at a time and keeps keys across connections. `SET` with
a zero TTL never expires; a positive TTL expires the key lazily when it is
read or its slot is needed. It returns `ERROR` for malformed or oversized
commands and when all 1024 slots hold live entries.

## Test

Run the cache tests from the project root:

```bash
python -m unittest discover -s in-mem-cache/tests -v
```

The test suite builds a temporary binary with strict compiler warnings.

## ADRs

Architecture Decision Records live in [`adr/`](adr/).

ADR filenames use a zero-padded number and lowercase slug, for example:

```text
adr/001-short-description.md
```
