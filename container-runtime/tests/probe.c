#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static volatile sig_atomic_t received_signal;

static void record_signal(int number) {
    received_signal = number;
}

static void inspect(char **arguments) {
    int leaked_fd = fcntl(atoi(arguments[4]), F_GETFD);
    printf("inherited_fd_closed=%d\n", leaked_fd < 0 && errno == EBADF);
    printf("pid=%ld\nppid=%ld\nuid=%ld\n", (long)getpid(), (long)getppid(), (long)getuid());
    char path[1024];
    if (getcwd(path, sizeof(path)) != NULL) {
        printf("cwd=%s\n", path);
    }
    struct stat info;
    if (stat("/proc/self/ns/pid", &info) == 0) {
        printf("pid_namespace=%lu\n", (unsigned long)info.st_ino);
    }
    if (stat("/proc/self/ns/mnt", &info) == 0) {
        printf("mount_namespace=%lu\n", (unsigned long)info.st_ino);
    }
    printf("rootfs_marker=%d\n", access("/marker", R_OK) == 0);
    printf("host_marker_hidden=%d\n", access(arguments[2], F_OK) < 0);
    snprintf(path, sizeof(path), "/proc/%s", arguments[3]);
    printf("host_process_hidden=%d\n", access(path, F_OK) < 0);

    DIR *directory = opendir("/proc/1/fd");
    int init_fds_closed = directory != NULL;
    if (directory != NULL) {
        struct dirent *entry;
        while ((entry = readdir(directory)) != NULL) {
            if (atoi(entry->d_name) >= 3) {
                init_fds_closed = 0;
            }
        }
        closedir(directory);
    }
    printf("init_fds_closed=%d\n", init_fds_closed);
    FILE *status = fopen("/proc/self/status", "r");
    if (status != NULL) {
        while (fgets(path, sizeof(path), status) != NULL) {
            if (strncmp(path, "Cap", 3) == 0 || strncmp(path, "NoNewPrivs:", 11) == 0) {
                fputs(path, stdout);
            }
        }
        fclose(status);
    }
}

static int orphan(void) {
    int result[2];
    if (pipe(result) < 0) {
        return 1;
    }
    pid_t intermediate = fork();
    if (intermediate < 0) {
        return 1;
    }
    if (intermediate == 0) {
        pid_t grandchild = fork();
        if (grandchild < 0) {
            _exit(1);
        }
        if (grandchild == 0) {
            usleep(50000);
            _exit(0);
        }
        if (write(result[1], &grandchild, sizeof(grandchild)) != sizeof(grandchild)) {
            _exit(1);
        }
        _exit(0);
    }
    close(result[1]);
    pid_t grandchild;
    if (read(result[0], &grandchild, sizeof(grandchild)) != sizeof(grandchild)) {
        return 1;
    }
    close(result[0]);
    waitpid(intermediate, NULL, 0);
    char path[64];
    snprintf(path, sizeof(path), "/proc/%ld", (long)grandchild);
    for (int attempt = 0; attempt < 200; attempt++) {
        if (access(path, F_OK) < 0 && errno == ENOENT) {
            puts("orphan reaped");
            return 0;
        }
        usleep(10000);
    }
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return 1;
    }
    if (strcmp(argv[1], "inspect") == 0 && argc == 5) {
        inspect(argv);
        return 0;
    }
    if (strcmp(argv[1], "exit") == 0 && argc == 3) {
        return atoi(argv[2]);
    }
    if (strcmp(argv[1], "orphan") == 0) {
        return orphan();
    }
    if (strcmp(argv[1], "signal") == 0) {
        struct sigaction action = {.sa_handler = record_signal};
        sigemptyset(&action.sa_mask);
        sigaction(SIGTERM, &action, NULL);
        sigaction(SIGINT, &action, NULL);
        pid_t child = fork();
        if (child < 0) {
            return 1;
        }
        if (child != 0) {
            puts("ready");
            fflush(stdout);
        }
        while (!received_signal) {
            usleep(10000);
        }
        if (child == 0) {
            FILE *marker = fopen("/child-signal", "w");
            if (marker == NULL) {
                return 1;
            }
            fprintf(marker, "%d\n", received_signal);
            fclose(marker);
            return 0;
        }
        waitpid(child, NULL, 0);
        return 128 + received_signal;
    }
    if (strcmp(argv[1], "tree") == 0) {
        int ready[2];
        if (pipe(ready) < 0) {
            return 1;
        }
        pid_t child = fork();
        if (child < 0) {
            return 1;
        }
        if (child == 0) {
            close(ready[0]);
            if (setsid() < 0 || write(ready[1], "1", 1) != 1) {
                return 1;
            }
            close(ready[1]);
            for (;;) {
                pause();
            }
        }
        close(ready[1]);
        char token;
        if (read(ready[0], &token, 1) != 1) {
            return 1;
        }
        close(ready[0]);
        puts("ready");
        fflush(stdout);
        return getchar() == 'x' ? 37 : 1;
    }
    return 1;
}
