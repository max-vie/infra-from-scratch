# Run the integrated cache in the container runtime

Last updated: 29.09.2026

## Summary

Launch the existing C cache through the Linux container runtime in the stack
integration suite. Build its rootfs from the freshly compiled cache and its
local loader and shared libraries.

## Context

The HTTP cache-aside adapter already uses the cache's TCP protocol, and the
container runtime already supports a supplied rootfs and namespace cleanup.
The stack suite currently launches the cache directly, so it does not exercise
the runtime with an existing service.

A static cache build would require a static C library that is absent on some
development hosts. Copying the trusted binary's dynamic dependencies follows
the rootfs pattern used by the runtime's own tests and requires no downloaded
image or package installation.

## Decision

In `integration-tests/test_stack.py`, compile the cache and runtime with strict
warnings. Prepare a temporary rootfs containing `/cache-server`, the loader and
libraries resolved by `ldd` on that binary, and a real `proc/` directory. Start
the cache through the runtime and pass its loopback port to the HTTP backends.

Use the runtime's existing user, PID, and mount isolation and shared host
network. Keep the existing cache protocol and HTTP cache-aside policy. Verify
cache population and hits through DNS, proxy, balancer, and HTTP servers, then
verify namespace and rootfs identity and cleanup with an active cache client.

On Ubuntu CI, run the runtime and stack suites in the same step while the
existing executable-specific AppArmor profile is loaded. Both suites rebuild
the configured temporary launcher path. Remove the profile when that step ends.

## Consequences

The integrated cache now exercises the runtime with the real threaded service.
Stopping the launcher terminates the cache and its client threads, releases the
listener, and removes its namespace mounts. Temporary rootfs files are removed
after the class finishes, including on test setup failure.

The integration suite now requires Linux with working unprivileged namespaces
and `ldd`, as the runtime suite does. The supplied code and copied libraries are
trusted local inputs. Networking and kernel access remain shared with the host.

## References

- [Cache-aside decision](002-use-an-optional-cache-aside-path-for-one-http-route.md)
- [Runtime lifecycle decision](../../container-runtime/docs/adr/001-run-one-command-in-linux-namespaces.md)
- [Cache README](../../in-mem-cache/README.md)
- [Runtime README](../../container-runtime/README.md)
