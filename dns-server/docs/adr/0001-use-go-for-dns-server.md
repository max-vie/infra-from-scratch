# Use Go for the DNS server

The DNS server will be implemented in Go instead of Python. Go's standard library supports long-running network services with a small standalone binary, and CoreDNS provides a relevant Go-based DNS precedent. The HTTP server remains implemented in Python, so this decision applies only to the DNS component.
