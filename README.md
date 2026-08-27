# infra-from-scratch

A hands-on project for rebuilding small Linux and cloud infrastructure components, mostly in Python.

## Components

- HTTP server
- DNS server
- Reverse proxy
- Load balancer
- In-memory cache
- Container runtime

## Initial stack

The planned first stack is:

```text
Client -> DNS -> Load balancer -> HTTP servers -> In-memory cache
```

The components will be connected with integration tests after the basic path works. Failure handling and observability come next.

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
