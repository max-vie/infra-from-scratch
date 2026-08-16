# infra-from-scratch

A hands-on project for rebuilding small Linux and cloud infrastructure components, mainly in Python.

## Components

- HTTP server
- DNS server
- Reverse proxy
- Load balancer
- Redis clone
- Container runtime

## Initial stack

The first version of the stack is planned as:

```text
Client -> DNS -> Load balancer -> HTTP servers -> Redis
```

Later work will connect the components with integration tests and add failure handling and observability.

## Possible additions

| Directory | Description |
| --- | --- |
| `service-discovery/` | Register services, send heartbeats, and healthchecks. |
| `message-queue/` | Support producers and consumers with acknowledgements and retries, similar to a small RabbitMQ or SQS concept. |
| `object-storage/` | Store and retrieve objects with metadata, checksums, and basic persistence, similar to a small S3. |
| `metrics-server/` | Expose counters, gauges, and latency data for scraping, similar to a small Prometheus-style system. |
| `scheduler/` | Assign workloads to available nodes based on their resources, similar to a small Kubernetes scheduler. |
| `certificate-authority/` | Issue and sign certificates for TLS between services. |

## Longer-term stack

The longer-term stack may look like this:

```text
HTTP, DNS, reverse proxy, load balancer, Redis, container runtime
    -> service discovery, message queue, metrics, scheduler
```

## Programming languages

- main: `python`
- supporting (conceptual for now): `go`, `c`, `rust`, `js`
