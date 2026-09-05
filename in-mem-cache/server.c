#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_HOST "127.0.0.1"
#define DEFAULT_PORT 11211
#define LINE_MAX (64 * 1024)
#define KEY_MAX 256
#define VALUE_MAX 4096
#define STORE_CAP 1024
#define TTL_MAX 86400
#define RECV_BUF 4096

struct entry {
    int used;
    char key[KEY_MAX + 1];
    char value[VALUE_MAX + 1];
    size_t vlen;
    long long expires_at_ms;
    int has_expiry;
};

static struct entry store[STORE_CAP];

static long long now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL;
}

static int lookup(const char *key, long long now) {
    for (int i = 0; i < STORE_CAP; i++) {
        if (store[i].used && strcmp(store[i].key, key) == 0) {
            /* Expiry is lazy: discard a stale entry when a command finds it. */
            if (store[i].has_expiry && now >= store[i].expires_at_ms) {
                store[i].used = 0;
                return -1;
            }
            return i;
        }
    }
    return -1;
}

static int free_slot(long long now) {
    for (int i = 0; i < STORE_CAP; i++) {
        if (!store[i].used ||
            (store[i].has_expiry && now >= store[i].expires_at_ms)) {
            store[i].used = 0;
            return i;
        }
    }
    return -1;
}

static int send_all(int fd, const char *buf, size_t len) {
    size_t sent = 0;
    /* A successful send may still write only part of the reply. */
    while (sent < len) {
        ssize_t n = send(fd, buf + sent, len - sent, 0);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (n == 0) {
            return -1;
        }
        sent += (size_t)n;
    }
    return 0;
}

static int send_reply(int fd, const char *fmt, ...) {
    char buf[VALUE_MAX + 32];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sizeof(buf)) {
        return send_all(fd, "ERROR\n", 6);
    }
    return send_all(fd, buf, (size_t)n);
}

static int valid_key(const char *key, size_t len) {
    if (len == 0 || len > KEY_MAX) {
        return 0;
    }
    for (size_t i = 0; i < len; i++) {
        unsigned char c = (unsigned char)key[i];
        if (isspace(c)) {
            return 0;
        }
    }
    return 1;
}

static int parse_ttl(const char *s, size_t len, long *out) {
    if (len == 0 || len > 5) {
        return 0;
    }
    for (size_t i = 0; i < len; i++) {
        if (!isdigit((unsigned char)s[i])) {
            return 0;
        }
    }
    char tmp[8];
    memcpy(tmp, s, len);
    tmp[len] = '\0';
    char *end = NULL;
    long v = strtol(tmp, &end, 10);
    if (end == tmp || *end != '\0' || v < 0 || v > TTL_MAX) {
        return 0;
    }
    *out = v;
    return 1;
}

/* Handle one stripped line (no trailing \n, no trailing \r). */
static int handle_line(int fd, char *line) {
    long long now = now_ms();

    if (strncmp(line, "GET ", 4) == 0) {
        char *key = line + 4;
        if (!valid_key(key, strlen(key))) {
            return send_reply(fd, "ERROR\n");
        }
        int idx = lookup(key, now);
        if (idx < 0) {
            return send_reply(fd, "NOT_FOUND\n");
        }
        return send_reply(fd, "VALUE %s\n", store[idx].value);
    }

    if (strncmp(line, "DELETE ", 7) == 0) {
        char *key = line + 7;
        if (!valid_key(key, strlen(key))) {
            return send_reply(fd, "ERROR\n");
        }
        int idx = lookup(key, now);
        if (idx < 0) {
            return send_reply(fd, "NOT_FOUND\n");
        }
        store[idx].used = 0;
        return send_reply(fd, "OK\n");
    }

    if (strncmp(line, "SET ", 4) == 0) {
        char *p = line + 4;
        char *sp1 = strchr(p, ' ');
        if (sp1 == NULL) {
            return send_reply(fd, "ERROR\n");
        }
        size_t klen = (size_t)(sp1 - p);
        if (!valid_key(p, klen)) {
            return send_reply(fd, "ERROR\n");
        }
        char key[KEY_MAX + 1];
        memcpy(key, p, klen);
        key[klen] = '\0';

        char *ts = sp1 + 1;
        char *sp2 = strchr(ts, ' ');
        if (sp2 == NULL) {
            return send_reply(fd, "ERROR\n");
        }
        long ttl = 0;
        if (!parse_ttl(ts, (size_t)(sp2 - ts), &ttl)) {
            return send_reply(fd, "ERROR\n");
        }
        char *value = sp2 + 1;
        size_t vlen = strlen(value);
        if (vlen == 0 || vlen > VALUE_MAX) {
            return send_reply(fd, "ERROR\n");
        }

        int idx = lookup(key, now);
        if (idx < 0) {
            idx = free_slot(now);
            if (idx < 0) {
                return send_reply(fd, "ERROR\n");
            }
        }
        memcpy(store[idx].key, key, klen + 1);
        memcpy(store[idx].value, value, vlen + 1);
        store[idx].vlen = vlen;
        store[idx].used = 1;
        if (ttl == 0) {
            store[idx].has_expiry = 0;
        } else {
            store[idx].has_expiry = 1;
            store[idx].expires_at_ms = now + ttl * 1000LL;
        }
        return send_reply(fd, "OK\n");
    }

    return send_reply(fd, "ERROR\n");
}

static void handle_client(int fd) {
    /* The server is single-threaded, so one reusable buffer is sufficient. */
    static char pending[LINE_MAX + 1];
    size_t pending_len = 0;
    char chunk[RECV_BUF];

    for (;;) {
        ssize_t n = recv(fd, chunk, sizeof(chunk), 0);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            return;
        }
        if (n == 0) {
            return;
        }
        if (pending_len + (size_t)n > LINE_MAX) {
            send_all(fd, "ERROR\n", 6);
            return;
        }
        memcpy(pending + pending_len, chunk, (size_t)n);
        pending_len += (size_t)n;

        size_t processed = 0;
        for (;;) {
            char *nl = memchr(pending + processed, '\n', pending_len - processed);
            if (nl == NULL) {
                break;
            }
            size_t linelen = (size_t)(nl - (pending + processed));
            char line[LINE_MAX + 1];
            memcpy(line, pending + processed, linelen);
            processed += linelen + 1;
            if (memchr(line, '\0', linelen) != NULL) {
                if (send_all(fd, "ERROR\n", 6) != 0) {
                    return;
                }
                continue;
            }
            line[linelen] = '\0';
            if (linelen > 0 && line[linelen - 1] == '\r') {
                line[linelen - 1] = '\0';
            }
            if (line[0] == '\0') {
                if (send_all(fd, "ERROR\n", 6) != 0) {
                    return;
                }
                continue;
            }
            if (handle_line(fd, line) != 0) {
                return;
            }
        }
        if (processed > 0) {
            memmove(pending, pending + processed, pending_len - processed);
            pending_len -= processed;
        }
        if (pending_len > LINE_MAX) {
            send_all(fd, "ERROR\n", 6);
            return;
        }
    }
}

static void usage(const char *prog) {
    fprintf(stderr,
            "Usage: %s [--listen-host HOST] [--listen-port PORT]\n",
            prog);
}

int main(int argc, char **argv) {
    const char *host = DEFAULT_HOST;
    int port = DEFAULT_PORT;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--listen-host") == 0 && i + 1 < argc) {
            host = argv[++i];
        } else if (strcmp(argv[i], "--listen-port") == 0 && i + 1 < argc) {
            char *end = NULL;
            long v = strtol(argv[++i], &end, 10);
            if (end == NULL || *end != '\0' || v < 1 || v > 65535) {
                fprintf(stderr, "port must be between 1 and 65535\n");
                return 2;
            }
            port = (int)v;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    signal(SIGPIPE, SIG_IGN);

    int listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) {
        perror("socket");
        return 1;
    }
    int one = 1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1) {
        fprintf(stderr, "invalid listen host: %s\n", host);
        close(listener);
        return 2;
    }
    if (bind(listener, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        perror("bind");
        close(listener);
        return 1;
    }
    if (listen(listener, 1) != 0) {
        perror("listen");
        close(listener);
        return 1;
    }
    printf("serving cache on %s:%d ...\n", host, port);
    fflush(stdout);

    /* Serve one connection at a time while the process-wide store persists. */
    for (;;) {
        int client = accept(listener, NULL, NULL);
        if (client < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("accept");
            continue;
        }
        handle_client(client);
        close(client);
    }
}
