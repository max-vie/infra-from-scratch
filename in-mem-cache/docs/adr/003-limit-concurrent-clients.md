# Limit concurrent cache clients

Last updated: 19.09.2026

## Summary

Accept up to 32 simultaneous cache clients. Send `ERROR` and close connections
accepted while every client slot is occupied.

## Context

[`002-handle-concurrent-clients.md`](002-handle-concurrent-clients.md) gives
each connection a detached POSIX thread. Idle clients can therefore consume
threads without bound as new connections arrive.

The cache is a small learning service with fixed storage and message limits. A
fixed client limit gives its thread usage the same explicit ceiling without
adding a worker pool or queue.

## Decision

Reserve a client slot after `accept` and before allocating thread state. Reject
the connection with the existing `ERROR` response when all 32 slots are in use.
Release the slot after the client handler closes its socket, and also release it
when allocation or thread creation fails.

Keep the thread-per-connection model, persistent connections, command protocol,
store mutex, and storage behavior. Do not add idle timeouts, a worker pool, a
waiting queue, or a configurable limit.

## Consequences

The server has a fixed ceiling of 32 client threads. Existing clients continue
to operate when the limit is reached, and a disconnected client makes its slot
available again. Clients may receive `ERROR` before sending a command when the
server is full.

The black-box suite fills every slot with incomplete requests, checks the
overload response, verifies an admitted client still works, and confirms a new
connection succeeds after one client disconnects.

## References

- [`002-handle-concurrent-clients.md`](002-handle-concurrent-clients.md)
- [POSIX `pthread_create`](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_create.html)
