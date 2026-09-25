package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	defaultListenHost = "127.0.0.1"
	defaultListenPort = 8000
	backendCount      = 2
	bufferSize        = 4096
	maxRequestSize    = 64 * 1024
	socketTimeout     = 5 * time.Second
	healthCooldown    = 1 * time.Second
	backendLease      = 3 * time.Second
	maxBackends       = 32
	maxAddressSize    = 128
)

var unsupportedBodyHeaders = []string{"content-length", "transfer-encoding"}

var errRequestTooLarge = errors.New("request headers are too large")

type backendFlags []string

type backendState struct {
	address   string
	retryAt   time.Time
	expiresAt time.Time
}

type backendPool struct {
	backends []*backendState
	mutex    sync.Mutex
}

func newBackendPool(addresses []string) *backendPool {
	pool := &backendPool{}
	for _, address := range addresses {
		pool.backends = append(pool.backends, &backendState{address: address})
	}
	return pool
}

func (pool *backendPool) pruneExpired(now time.Time) {
	active := pool.backends[:0]
	for _, backend := range pool.backends {
		if backend.expiresAt.IsZero() || now.Before(backend.expiresAt) {
			active = append(active, backend)
		}
	}
	pool.backends = active
}

func (pool *backendPool) snapshot() []*backendState {
	pool.mutex.Lock()
	defer pool.mutex.Unlock()
	pool.pruneExpired(time.Now())
	return append([]*backendState(nil), pool.backends...)
}

func (pool *backendPool) register(address string) error {
	pool.mutex.Lock()
	defer pool.mutex.Unlock()
	now := time.Now()
	pool.pruneExpired(now)
	for _, backend := range pool.backends {
		if backend.address == address {
			backend.expiresAt = now.Add(backendLease)
			return nil
		}
	}
	if len(pool.backends) >= maxBackends {
		return errors.New("backend limit reached")
	}
	pool.backends = append(pool.backends, &backendState{
		address: address, expiresAt: now.Add(backendLease),
	})
	return nil
}

func (pool *backendPool) remove(address string) bool {
	pool.mutex.Lock()
	defer pool.mutex.Unlock()
	for index, backend := range pool.backends {
		if backend.address == address {
			pool.backends = append(pool.backends[:index], pool.backends[index+1:]...)
			return true
		}
	}
	return false
}

func (pool *backendPool) available(backend *backendState) bool {
	pool.mutex.Lock()
	defer pool.mutex.Unlock()
	now := time.Now()
	return (backend.expiresAt.IsZero() || now.Before(backend.expiresAt)) &&
		(backend.retryAt.IsZero() || !now.Before(backend.retryAt))
}

func (pool *backendPool) markFailure(backend *backendState) {
	pool.mutex.Lock()
	backend.retryAt = time.Now().Add(healthCooldown)
	pool.mutex.Unlock()
}

func (pool *backendPool) markSuccess(backend *backendState) {
	pool.mutex.Lock()
	backend.retryAt = time.Time{}
	pool.mutex.Unlock()
}

func (flags *backendFlags) String() string {
	return strings.Join(*flags, ", ")
}

func (flags *backendFlags) Set(value string) error {
	*flags = append(*flags, value)
	return nil
}

func main() {
	// Keep listener and backend addresses configurable for local experiments.
	listenHost := flag.String("listen-host", defaultListenHost, "address to bind")
	listenPort := flag.Int("listen-port", defaultListenPort, "port to bind (1-65535)")
	registryPort := flag.Int("registry-port", 0, "local backend registry port (1-65535)")
	var backends backendFlags
	flag.Var(&backends, "backend", "backend as HOST:PORT (required twice without registry)")
	flag.Parse()

	listenAddress, err := hostPort(*listenHost, *listenPort)
	if err != nil {
		fatal(err)
	}
	if *registryPort == 0 && len(backends) != backendCount {
		fatal(errors.New("exactly two --backend options are required"))
	}
	if *registryPort != 0 && len(backends) != 0 {
		fatal(errors.New("--backend cannot be used with --registry-port"))
	}
	if *registryPort < 0 || *registryPort > 65535 {
		fatal(errors.New("registry port must be between 1 and 65535"))
	}
	backendAddresses := make([]string, 0, backendCount)
	for _, backend := range backends {
		address, err := backendAddress(backend)
		if err != nil {
			fatal(err)
		}
		backendAddresses = append(backendAddresses, address)
	}

	if err := serve(listenAddress, backendAddresses, *registryPort); err != nil {
		fatal(err)
	}
}

func backendAddress(value string) (string, error) {
	host, rawPort, ok := strings.Cut(value, ":")
	if !ok || host == "" || rawPort == "" {
		return "", fmt.Errorf("backend must be HOST:PORT: %q", value)
	}
	port, err := strconv.Atoi(rawPort)
	if err != nil {
		return "", fmt.Errorf("backend must be HOST:PORT: %q", value)
	}
	return hostPort(host, port)
}

func hostPort(host string, port int) (string, error) {
	if port < 1 || port > 65535 {
		return "", fmt.Errorf("port must be between 1 and 65535")
	}
	return net.JoinHostPort(host, strconv.Itoa(port)), nil
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(2)
}

func serve(listenAddress string, backendAddresses []string, registryPort int) error {
	// Listen for local TCP connections.
	listener, err := net.Listen("tcp", listenAddress)
	if err != nil {
		return err
	}
	defer listener.Close()
	pool := newBackendPool(backendAddresses)
	if registryPort != 0 {
		registryAddress := net.JoinHostPort("127.0.0.1", strconv.Itoa(registryPort))
		registry, err := net.Listen("tcp", registryAddress)
		if err != nil {
			return err
		}
		defer registry.Close()
		go func() {
			server := http.Server{
				Handler:           registryHandler(pool),
				ReadHeaderTimeout: 2 * time.Second,
				ReadTimeout:       2 * time.Second,
			}
			if err := server.Serve(registry); err != nil {
				fmt.Fprintln(os.Stderr, err)
			}
		}()
	}

	fmt.Printf(
		"serving load balancer on %s with %d backends\n",
		listenAddress,
		len(backendAddresses),
	)

	// Handle each client independently so a slow request cannot block others.
	var selection atomic.Uint64
	for {
		client, err := listener.Accept()
		if err != nil {
			continue
		}
		go func(connection net.Conn) {
			defer connection.Close()
			handleConnection(connection, pool, &selection)
		}(client)
	}
}

func registryHandler(pool *backendPool) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/backends" {
			http.NotFound(writer, request)
			return
		}
		if request.Method == http.MethodGet {
			for _, backend := range pool.snapshot() {
				fmt.Fprintln(writer, backend.address)
			}
			return
		}
		if request.Method != http.MethodPut && request.Method != http.MethodDelete {
			writer.Header().Set("Allow", "GET, PUT, DELETE")
			http.Error(writer, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		body, err := io.ReadAll(io.LimitReader(request.Body, maxAddressSize+1))
		if err != nil || len(body) > maxAddressSize {
			http.Error(writer, "invalid backend address", http.StatusBadRequest)
			return
		}
		address, err := backendAddress(strings.TrimSpace(string(body)))
		if err != nil {
			http.Error(writer, "invalid backend address", http.StatusBadRequest)
			return
		}
		host, _, _ := net.SplitHostPort(address)
		if net.ParseIP(host).To4() == nil {
			http.Error(writer, "backend address must use IPv4", http.StatusBadRequest)
			return
		}
		if request.Method == http.MethodPut {
			if err := pool.register(address); err != nil {
				http.Error(writer, err.Error(), http.StatusConflict)
				return
			}
		} else if !pool.remove(address) {
			http.Error(writer, "backend not found", http.StatusNotFound)
			return
		}
		writer.WriteHeader(http.StatusNoContent)
	})
}

func handleConnection(client net.Conn, pool *backendPool, selection *atomic.Uint64) {
	// Validate the request before choosing a backend.
	_ = client.SetDeadline(time.Now().Add(socketTimeout))

	request, err := readRequest(client)
	invalid := err != nil || len(request) == 0 ||
		!bytes.Contains(request, []byte("\r\n\r\n")) ||
		hasUnsupportedBody(request)
	if invalid {
		sendError(client, "400 Bad Request", []byte("Bad Request\n"))
		return
	}

	// Claim this request's starting backend so concurrent clients still alternate.
	backends := pool.snapshot()
	if len(backends) == 0 {
		sendError(client, "502 Bad Gateway", []byte("Bad Gateway\n"))
		return
	}
	initialIndex := int(selection.Add(1)-1) % len(backends)
	for offset := range len(backends) {
		selected := backends[(initialIndex+offset)%len(backends)]
		if !pool.available(selected) {
			continue
		}
		responseStarted := false

		backend, err := net.DialTimeout("tcp", selected.address, socketTimeout)
		if err == nil {
			_ = backend.SetDeadline(time.Now().Add(socketTimeout))
			err = relay(backend, client, request, &responseStarted)
			backend.Close()
		}
		if err == nil {
			pool.markSuccess(selected)
			return
		}
		if responseStarted {
			// Response bytes already reached the client; do not retry
			// or append another error.
			return
		}
		pool.markFailure(selected)
	}
	sendError(client, "502 Bad Gateway", []byte("Bad Gateway\n"))
}

func relay(backend, client net.Conn, request []byte, responseStarted *bool) error {
	// Forward the request and relay the response until the backend closes.
	if _, err := backend.Write(request); err != nil {
		return err
	}
	if tcp, ok := backend.(*net.TCPConn); ok {
		_ = tcp.CloseWrite()
	}

	buffer := make([]byte, bufferSize)
	for {
		size, err := backend.Read(buffer)
		if size > 0 {
			if _, writeErr := client.Write(buffer[:size]); writeErr != nil {
				return writeErr
			}
			*responseStarted = true
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				return nil
			}
			return err
		}
	}
}

func readRequest(connection net.Conn) ([]byte, error) {
	// Read one header-terminated request with a bounded buffer.
	request := make([]byte, 0, bufferSize)
	chunk := make([]byte, bufferSize)
	headerEnd := -1
	for headerEnd == -1 {
		size, err := connection.Read(chunk)
		if size > 0 {
			request = append(request, chunk[:size]...)
			headerEnd = bytes.Index(request, []byte("\r\n\r\n"))
			if headerEnd == -1 && len(request) > maxRequestSize {
				return nil, errRequestTooLarge
			}
		}
		if err != nil {
			return request, err
		}
	}
	headerEnd += 4
	if headerEnd > maxRequestSize {
		return nil, errRequestTooLarge
	}
	return request[:headerEnd], nil
}

func hasUnsupportedBody(request []byte) bool {
	// Reject request framing that the first load balancer does not implement.
	headers, _, _ := bytes.Cut(request, []byte("\r\n\r\n"))
	lines := bytes.Split(headers, []byte("\r\n"))[1:]
	for _, line := range lines {
		name, _, _ := bytes.Cut(line, []byte(":"))
		key := string(bytes.TrimSpace(bytes.ToLower(name)))
		for _, unsupported := range unsupportedBodyHeaders {
			if key == unsupported {
				return true
			}
		}
	}
	return false
}

func sendError(connection net.Conn, status string, body []byte) {
	// Send an HTTP/1.0 error response and close the connection afterward.
	response := fmt.Sprintf(
		"HTTP/1.0 %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n",
		status,
		len(body),
	)
	_, _ = connection.Write(append([]byte(response), body...))
}
