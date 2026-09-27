#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define STACK_SIZE (1024 * 1024)
#define RUNTIME_ERROR 125

static const int forwarded_signals[] = {SIGINT, SIGTERM, SIGHUP, SIGQUIT};
static sigset_t wait_signals;

struct container {
    int root_fd;
    char *root_path;
    int parent_fd;
    int ready[2];
    char **command;
};

static void fail(const char *operation) {
    perror(operation);
    _exit(RUNTIME_ERROR);
}

static void signal_handler(int signal_number) {
    (void)signal_number;
}

static int exit_status(int status) {
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}

static int supervise(pid_t child, int process_group) {
    for (;;) {
        int status;
        pid_t reaped;
        while ((reaped = waitpid(-1, &status, WNOHANG)) > 0) {
            if (reaped == child) {
                return exit_status(status);
            }
        }
        if (reaped < 0 && errno != EINTR) {
            fail("waitpid");
        }
        int received = sigwaitinfo(&wait_signals, NULL);
        if (received < 0) {
            if (errno == EINTR) {
                continue;
            }
            fail("sigwaitinfo");
        }
        if (received != SIGCHLD &&
            kill(process_group ? -child : child, received) < 0 && errno != ESRCH) {
            fail("forward signal");
        }
    }
}

static void drop_capabilities(void) {
    for (int capability = 0;; capability++) {
        if (prctl(PR_CAPBSET_READ, capability, 0, 0, 0) < 0) {
            if (errno == EINVAL) {
                break;
            }
            fail("read capability bounding set");
        }
        if (prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) < 0) {
            fail("drop capability bounding set");
        }
    }
    struct __user_cap_header_struct header = {
        .version = _LINUX_CAPABILITY_VERSION_3,
        .pid = 0,
    };
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    if (syscall(SYS_capset, &header, data) < 0 ||
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) < 0) {
        fail("drop process privileges");
    }
}

static int run_container(void *argument) {
    struct container *container = argument;
    close(container->ready[1]);
    if (prctl(PR_SET_PDEATHSIG, SIGKILL) < 0) {
        fail("set parent death signal");
    }
    /* A pidfd also detects a parent that exited before prctl above. */
    struct pollfd parent = {.fd = container->parent_fd, .events = POLLIN};
    if (poll(&parent, 1, 0) != 0) {
        _exit(RUNTIME_ERROR);
    }
    close(container->parent_fd);
    char ready;
    if (read(container->ready[0], &ready, 1) != 1 || ready != '1') {
        _exit(RUNTIME_ERROR);
    }
    close(container->ready[0]);

    if (setsid() < 0) {
        fail("setsid");
    }
    /* All mount changes stay in this namespace, including on setup failure. */
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) < 0) {
        fail("make mounts private");
    }
    /* Reopen in the new mount namespace; inherited fds pin the parent's mounts. */
    int root = open(container->root_path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat expected, current;
    if (root < 0 || fstat(root, &current) < 0 || fstat(container->root_fd, &expected) < 0) {
        fail("reopen rootfs");
    }
    if (current.st_dev != expected.st_dev || current.st_ino != expected.st_ino) {
        errno = ESTALE;
        fail("rootfs changed during startup");
    }
    if (fchdir(root) < 0 || mount(".", ".", NULL, MS_BIND, NULL) < 0) {
        fail("bind rootfs");
    }
    if (chdir(container->root_path) < 0) {
        fail("enter rootfs mount");
    }
    if (stat(".", &current) < 0) {
        fail("stat rootfs mount");
    }
    if (current.st_dev != expected.st_dev || current.st_ino != expected.st_ino) {
        errno = ESTALE;
        fail("rootfs changed before pivot");
    }
    if (mount("proc", "proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) < 0) {
        fail("mount container proc");
    }
    if (syscall(SYS_pivot_root, ".", ".") < 0) {
        fail("pivot rootfs");
    }
    if (umount2(".", MNT_DETACH) < 0 || chdir("/") < 0) {
        fail("detach old root");
    }
    if (syscall(SYS_close_range, 3U, ~0U, 0) < 0) {
        fail("close inherited descriptors");
    }
    drop_capabilities();

    pid_t command = fork();
    if (command < 0) {
        fail("fork command");
    }
    if (command == 0) {
        if (setpgid(0, 0) < 0) {
            fail("set command process group");
        }
        struct sigaction action = {.sa_handler = SIG_DFL};
        sigemptyset(&action.sa_mask);
        for (size_t i = 0; i < sizeof(forwarded_signals) / sizeof(int); i++) {
            if (sigaction(forwarded_signals[i], &action, NULL) < 0) {
                fail("reset signal handler");
            }
        }
        if (sigaction(SIGPIPE, &action, NULL) < 0 ||
            sigprocmask(SIG_UNBLOCK, &wait_signals, NULL) < 0) {
            fail("reset command signals");
        }
        execv(container->command[0], container->command);
        int code = errno == ENOENT ? 127 : 126;
        perror("exec command");
        _exit(code);
    }
    if (setpgid(command, command) < 0 && errno != EACCES) {
        fail("set command process group");
    }
    /* Returning as PID 1 also kills any remaining namespace descendants. */
    return supervise(command, 1);
}

static int write_map(pid_t child, const char *name, const char *value) {
    char path[64];
    snprintf(path, sizeof(path), "/proc/%ld/%s", (long)child, name);
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) {
        return -1;
    }
    size_t length = strlen(value);
    ssize_t written = write(fd, value, length);
    int saved_errno = written < 0 ? errno : EIO;
    close(fd);
    if (written != (ssize_t)length) {
        errno = saved_errno;
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        printf("Usage: %s ROOTFS /COMMAND [ARG ...]\n", argv[0]);
        return 0;
    }
    if (argc < 3 || argv[2][0] != '/') {
        fprintf(stderr, "Usage: %s ROOTFS /COMMAND [ARG ...]\n", argv[0]);
        return RUNTIME_ERROR;
    }
    if (getuid() == 0 || getuid() != geteuid() || getgid() != getegid()) {
        fprintf(stderr, "run as an unprivileged user without setuid or setgid\n");
        return RUNTIME_ERROR;
    }
    for (int fd = 0; fd < 3; fd++) {
        if (fcntl(fd, F_GETFD) < 0) {
            fail("standard descriptor must be open");
        }
    }
    struct container container = {.command = &argv[2]};
    container.root_path = realpath(argv[1], NULL);
    if (container.root_path == NULL) {
        fail("resolve rootfs");
    }
    container.root_fd = open(container.root_path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (container.root_fd < 0) {
        fail("open rootfs");
    }
    struct stat rootfs, host_root;
    if (fstat(container.root_fd, &rootfs) < 0 || stat("/", &host_root) < 0) {
        fail("stat rootfs");
    }
    if (rootfs.st_dev == host_root.st_dev && rootfs.st_ino == host_root.st_ino) {
        fprintf(stderr, "rootfs must be a prepared directory other than /\n");
        return RUNTIME_ERROR;
    }
    int proc = openat(container.root_fd, "proc", O_PATH | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (proc < 0) {
        fail("rootfs needs a real proc directory");
    }
    close(proc);

    sigemptyset(&wait_signals);
    sigaddset(&wait_signals, SIGCHLD);
    for (size_t i = 0; i < sizeof(forwarded_signals) / sizeof(int); i++) {
        sigaddset(&wait_signals, forwarded_signals[i]);
    }
    if (sigprocmask(SIG_BLOCK, &wait_signals, NULL) < 0) {
        fail("block supervisor signals");
    }
    struct sigaction action = {.sa_handler = signal_handler};
    sigemptyset(&action.sa_mask);
    for (size_t i = 0; i < sizeof(forwarded_signals) / sizeof(int); i++) {
        if (sigaction(forwarded_signals[i], &action, NULL) < 0) {
            fail("set signal handler");
        }
    }
    action.sa_handler = SIG_DFL;
    if (sigaction(SIGCHLD, &action, NULL) < 0) {
        fail("reset SIGCHLD");
    }
    action.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &action, NULL) < 0) {
        fail("ignore SIGPIPE");
    }
    container.parent_fd = (int)syscall(SYS_pidfd_open, getpid(), 0);
    if (container.parent_fd < 0 || pipe2(container.ready, O_CLOEXEC) < 0) {
        fail("create startup descriptors");
    }
    char *stack = malloc(STACK_SIZE);
    if (stack == NULL) {
        fail("allocate child stack");
    }
    pid_t child = clone(run_container, stack + STACK_SIZE,
                       CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWPID | SIGCHLD,
                       &container);
    if (child < 0) {
        fail("create user, mount, and PID namespaces");
    }
    close(container.ready[0]);
    close(container.parent_fd);
    close(container.root_fd);
    char uid_map[64], gid_map[64];
    snprintf(uid_map, sizeof(uid_map), "0 %lu 1\n", (unsigned long)getuid());
    snprintf(gid_map, sizeof(gid_map), "0 %lu 1\n", (unsigned long)getgid());
    if (write_map(child, "setgroups", "deny") < 0 ||
        write_map(child, "uid_map", uid_map) < 0 ||
        write_map(child, "gid_map", gid_map) < 0 ||
        write(container.ready[1], "1", 1) != 1) {
        perror("map container user");
        kill(child, SIGKILL);
        while (waitpid(child, NULL, 0) < 0 && errno == EINTR) {}
        close(container.ready[1]);
        free(stack);
        free(container.root_path);
        return RUNTIME_ERROR;
    }
    close(container.ready[1]);
    int result = supervise(child, 0);
    free(stack);
    free(container.root_path);
    return result;
}
