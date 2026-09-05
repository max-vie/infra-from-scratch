# infra-from-scratch

A hands-on project for rebuilding small Linux and cloud infrastructure components, mostly in Python.

## Components

- HTTP server
- DNS server
- Reverse proxy
- Load balancer
- In-memory cache
- Container runtime

## Current integrated path

The first working path is:

```text
Client -> DNS -> Reverse proxy -> Load balancer -> HTTP servers
```

The integration smoke tests cover both the direct load-balancer path and the
full path through the reverse proxy using the resolved address.

The in-memory cache and container runtime remain planned components.

Run the integration test from the project root:

```bash
python -m unittest discover -s integration-tests -v
```

## Possible additions

| Directory | Description |
| --- | --- |
| `service-discovery/` | Register services, send heartbeats, and run health checks. |
| `message-queue/` | Support producers and consumers with acknowledgments and retries, similar to a small RabbitMQ or SQS service. |
| `object-storage/` | Store and retrieve objects with metadata, checksums, and basic persistence. |
| `metrics-server/` | Expose counters, gauges, and latency data for scraping, similar to a small Prometheus-style service. |
| `scheduler/` | Assign workloads to nodes based on available resources, similar to a small Kubernetes scheduler. |
| `certificate-authority/` | Issue and sign certificates for service-to-service TLS. |

## Later stack

Later work may add:

```text
HTTP, DNS, reverse proxy, load balancer, in-memory cache, container runtime
    -> service discovery, message queue, metrics, scheduler
```

## Programming languages

- main: `python`
- used by components: `go`
- future experiments: `c`, `rust`
