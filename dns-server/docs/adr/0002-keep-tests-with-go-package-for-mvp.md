# Keep tests with the Go package for the MVP

Last updated: 2026-08-18

The DNS MVP keeps `server_test.go` beside `server.go` so it can test the package's private response-building functions without adding a package, `cmd/`, or module layout. If the DNS server grows into a larger component, the structure can be changed to an importable package with a separate executable and test directory.
