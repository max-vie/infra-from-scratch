# Load balancer documentation

- [`adr/001-use-round-robin-backend-selection.md`](adr/001-use-round-robin-backend-selection.md)
  defines backend selection.
- [`adr/002-fail-over-to-other-backend-on-connection-failure.md`](adr/002-fail-over-to-other-backend-on-connection-failure.md)
  defines connection-failure handling.
- [`adr/003-use-go-for-load-balancer.md`](adr/003-use-go-for-load-balancer.md)
  replaces the original Python implementation with Go.

See the [component README](../README.md) for current behavior, run, and test
commands.
