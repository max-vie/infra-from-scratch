# Run one command in Linux namespaces

Last updated: 27.09.2026

## Summary

Build a C launcher that runs one command with a supplied root filesystem and
separate user, PID, and mount namespaces. Tie namespace lifetime to that command.

## Context

The project already exposes protocol boundaries through its socket servers.
The planned container component adds process and filesystem isolation using
Linux system calls and the existing GCC and Python test tooling.

A privileged launcher would require host root for its mounts. User namespaces
allow a normal caller to perform the required setup within a separate namespace.
Executing the command directly as PID 1 would burden it with signal handling
and orphan reaping, so a small init process owns those tasks.

## Decision

Implement `container-runtime/runtime.c` with a `ROOTFS /COMMAND [ARG ...]`
interface. Use `clone` to create user, PID, and mount namespaces. Map only the
caller's UID and GID, deny `setgroups`, and use a pipe to release the child after
mapping succeeds. Reject root and setuid/setgid invocation.

Reopen the rootfs in the child's mount namespace and check its identity against
the directory opened by the parent. Make mount propagation private, bind the
rootfs, mount a new proc filesystem, call `pivot_root`, and detach the old root.
Close inherited descriptors beyond standard I/O, clear capabilities, and set
`no_new_privs` before starting the command.

PID 1 starts the command in its own process group, forwards termination signals,
and reaps children. Both supervisors wait with blocked signals to avoid a gap
between child-exit checks and signal delivery. The command's status becomes the
launcher's status. When PID 1 exits, Linux terminates its remaining descendants.
A parent death signal plus an inherited parent pidfd handles launcher death,
including the race before the child can set its death signal.

Use only the C library and Linux interfaces. Require Linux 5.9 or newer for
`close_range`. The supplied rootfs and programs are trusted local inputs.
Networking, resource controls, image handling, OCI compatibility, seccomp, and
terminal job control remain separate decisions.

## Consequences

Mount setup and failure cleanup are confined to the new namespace. Files written
inside the supplied rootfs persist, while the temporary mounts disappear with
the namespace. Standard I/O can still refer to host resources, and the workload
shares the host network and kernel. Keep the input directory unchanged during
startup; this component does not promise a security boundary for hostile code.

The component's Python subprocess suite builds its own probe and a temporary
rootfs with the probe's local dynamic libraries. It checks process and root
isolation, status propagation, signal delivery, descriptor and capability
removal, orphan reaping, and descendant cleanup. CI must run those checks on a
Linux host with working unprivileged namespaces. CI fails when namespace
isolation is unavailable.

On Ubuntu CI, load an AppArmor profile granting user namespace permission to the
exact temporary launcher path, then remove it when the test step exits. The
runtime and its tests run as the unprivileged runner user. The test executable
is always rebuilt from current source.

## References

- [Component README](../../README.md)
- [Linux user namespaces](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)
- [Linux PID namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)
- [`pivot_root`](https://man7.org/linux/man-pages/man2/pivot_root.2.html)
- [Repository ADR format](../../../docs/adr/001-use-lean-nygard-inspired-adr-format.md)
