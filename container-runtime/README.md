# Container runtime

A small Linux launcher written in C. It runs one command inside a supplied root
filesystem with separate user, PID, and mount namespaces.

## Behavior

The launcher maps the calling user's UID and GID to zero inside the container.
The caller stays unprivileged on the host. All mount propagation becomes private
before the launcher bind-mounts the rootfs, mounts a fresh `/proc`, switches root
with `pivot_root`, and detaches the old filesystem.

An internal PID 1 starts the command as PID 2 and reaps orphaned children. The
launcher forwards `SIGINT`, `SIGTERM`, `SIGHUP`, and `SIGQUIT` to the command's
process group. When the command ends, any remaining processes in the namespace
are killed and the namespace mounts disappear. Killing the outer launcher also
kills its namespace init and remaining descendants.

The command inherits standard input, output, error, and environment. Other
inherited file descriptors are closed in PID 1 before the command starts. All
capabilities are dropped and `no_new_privs` is enabled. The command's working
directory is `/`.

The rootfs stays writable: files the command writes there persist in the supplied
directory. Use a prepared rootfs and trusted programs, and keep the rootfs and
its path unchanged during startup. Networking, resource limits, and kernel access
are shared with the host; this learning runtime is intended for local experiments
with trusted programs. It does not implement image downloads, OCI configuration,
seccomp filtering, cgroups, networking setup, or terminal job control.

## Build and run

Use Linux 5.9 or newer, GCC, and a host that permits unprivileged user namespaces.
The launcher rejects root, setuid, and setgid execution. No package installation
or third-party library is needed for the launcher itself.

```bash
gcc -std=c11 -Wall -Wextra -Werror -pedantic -O2 \
  -o container-runtime/runtime container-runtime/runtime.c
./container-runtime/runtime /path/to/rootfs /bin/echo hello
```

Supply a rootfs containing the command, its interpreter and shared libraries if
needed, and a real `proc/` directory. `/` itself is rejected as a rootfs. The
command path must be absolute inside that filesystem; arguments are passed
directly to it.

The exit code is the command's exit status, or `128 + signal` for signal
termination. Setup errors return 125, an executable that cannot be invoked
returns 126, and a missing executable or interpreter returns 127. Errors include
the failed setup operation on stderr. A host that denies namespace creation fails
before starting the command.

## Test

```bash
python -m unittest discover -s container-runtime/tests -v
```

The suite needs GCC, `ldd`, and working user namespaces. It compiles a trusted C
probe and copies its locally resolved loader and libraries into temporary
rootfs directories. It exercises actual namespace operations and does not skip
them when unavailable.

Ubuntu hosts can also require an AppArmor profile granting user namespace
permission to the launcher. CI loads a profile for one temporary runtime
executable and removes it after the test step. `CONTAINER_RUNTIME_TEST_BINARY`
selects that executable path; the suite still compiles the current source there
before every run. Local tests use a fresh temporary directory by default.

Tests verify the changed root and namespace identities, hidden host paths and
processes, descriptor closure, dropped privileges, exit statuses, signal
forwarding, orphan reaping, descendant termination, and rootfs reuse after a
failed exec. Host mount paths are checked after execution. Abrupt launcher death
leaves reaping of its dead namespace init to the host's init process.

## Documentation

- [Architecture decision](docs/adr/001-run-one-command-in-linux-namespaces.md)

## Sources

- [Linux user namespaces](https://man7.org/linux/man-pages/man7/user_namespaces.7.html)
- [Linux PID namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)
- [`pivot_root`](https://man7.org/linux/man-pages/man2/pivot_root.2.html)
- [`close_range`](https://man7.org/linux/man-pages/man2/close_range.2.html)
- [Parent death signals](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html)
- [Ubuntu AppArmor namespace restrictions](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/)
