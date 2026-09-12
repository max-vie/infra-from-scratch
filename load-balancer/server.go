package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"strconv"
	"strings"
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
)

var unsupportedBodyHeaders = []string{"content-length", "transfer-encoding"}

var errRequestTooLarge = errors.New("request headers are too large")

type backendFlags []string

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
	var backends backendFlags
	flag.Var(&backends, "backend", "backend as HOST:PORT (required twice)")
	flag.Parse()

	listenAddress, err := hostPort(*listenHost, *listenPort)
	if err != nil {
		fatal(err)
	}
	if len(backends) != backendCount {
		fatal(errors.New("exactly two --backend options are required"))
	}
	backendAddresses := make([]string, 0, backendCount)
	for _, backend := range backends {
		host, rawPort, ok := strings.Cut(backend, ":")
		if !ok || host == "" || rawPort == "" {
			fatal(fmt.Errorf("backend must be HOST:PORT: %q", backend))
		}
		port, err := strconv.Atoi(rawPort)
		if err != nil {
			fatal(fmt.Errorf("backend must be HOST:PORT: %q", backend))
		}
		address, err := hostPort(host, port)
		if err != nil {
			fatal(err)
		}
		backendAddresses = append(backendAddresses, address)
	}

	if err := serve(listenAddress, backendAddresses); err != nil {
		fatal(err)
	}
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

func serve(listenAddress string, backendAddresses []string) error {
	// Listen for local TCP connections.
	listener, err := net.Listen("tcp", listenAddress)
	if err != nil {
		return err
	}
	defer listener.Close()

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
			handleConnection(connection, backendAddresses, &selection)
		}(client)
	}
}

func handleConnection(client net.Conn, backendAddresses []string, selection *atomic.Uint64) {
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
	initialIndex := int(selection.Add(1)-1) % len(backendAddresses)
	for offset := range len(backendAddresses) {
		selectedBackend := backendAddresses[(initialIndex+offset)%len(backendAddresses)]
		responseStarted := false

		backend, err := net.DialTimeout("tcp", selectedBackend, socketTimeout)
		if err == nil {
			_ = backend.SetDeadline(time.Now().Add(socketTimeout))
			err = relay(backend, client, request, &responseStarted)
			backend.Close()
		}
		if err == nil {
			return
		}
		if responseStarted {
			// Response bytes already reached the client; do not retry
			// or append another error.
			return
		}
		if offset == len(backendAddresses)-1 {
			sendError(client, "502 Bad Gateway", []byte("Bad Gateway\n"))
		}
	}
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
