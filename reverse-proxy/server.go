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
	"time"
)

const (
	defaultListenHost  = "127.0.0.1"
	defaultListenPort  = 8080
	defaultBackendHost = "127.0.0.1"
	defaultBackendPort = 8088
	bufferSize         = 4096
	maxRequestSize     = 64 * 1024
	socketTimeout      = 5 * time.Second
)

var unsupportedBodyHeaders = []string{"content-length", "transfer-encoding"}

var errRequestTooLarge = errors.New("request headers are too large")

func main() {
	// Keep listener and backend addresses configurable for local experiments.
	listenHost := flag.String("listen-host", defaultListenHost, "address to bind")
	listenPort := flag.Int("listen-port", defaultListenPort, "port to bind (1-65535)")
	backendHost := flag.String("backend-host", defaultBackendHost, "backend address")
	backendPort := flag.Int("backend-port", defaultBackendPort, "backend port (1-65535)")
	flag.Parse()

	listenAddress, err := hostPort(*listenHost, *listenPort)
	if err != nil {
		fatal(err)
	}
	backendAddress, err := hostPort(*backendHost, *backendPort)
	if err != nil {
		fatal(err)
	}

	if err := serve(listenAddress, backendAddress); err != nil {
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

func serve(listenAddress, backendAddress string) error {
	// Listen for local TCP connections.
	listener, err := net.Listen("tcp", listenAddress)
	if err != nil {
		return err
	}
	defer listener.Close()

	fmt.Printf("serving reverse proxy on %s to %s\n", listenAddress, backendAddress)

	// Handle each client independently so a slow request cannot block others.
	for {
		client, err := listener.Accept()
		if err != nil {
			continue
		}
		go func(connection net.Conn) {
			defer connection.Close()
			handleConnection(connection, backendAddress)
		}(client)
	}
}

func handleConnection(client net.Conn, backendAddress string) {
	// Read the request before opening the backend connection.
	_ = client.SetDeadline(time.Now().Add(socketTimeout))

	request, err := readRequest(client)
	if err != nil || len(request) == 0 || !bytes.Contains(request, []byte("\r\n\r\n")) {
		// Reject malformed, oversized, or incomplete requests.
		sendError(client, "400 Bad Request", []byte("Bad Request\n"))
		return
	}
	if hasUnsupportedBody(request) {
		sendError(client, "400 Bad Request", []byte("Bad Request\n"))
		return
	}

	responseStarted := false
	backend, err := net.DialTimeout("tcp", backendAddress, socketTimeout)
	if err == nil {
		defer backend.Close()
		_ = backend.SetDeadline(time.Now().Add(socketTimeout))
		err = relay(backend, client, request, &responseStarted)
	}
	if err != nil && !responseStarted {
		status := "502 Bad Gateway"
		body := []byte("Bad Gateway\n")
		var timeoutError net.Error
		if errors.As(err, &timeoutError) && timeoutError.Timeout() {
			status = "504 Gateway Timeout"
			body = []byte("Gateway Timeout\n")
		}
		_ = client.SetWriteDeadline(time.Now().Add(socketTimeout))
		sendError(client, status, body)
	}
}

func relay(backend, client net.Conn, request []byte, responseStarted *bool) error {
	// Forward the raw request and relay the backend response.
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
	for !bytes.Contains(request, []byte("\r\n\r\n")) {
		size, err := connection.Read(chunk)
		if size > 0 {
			request = append(request, chunk[:size]...)
			if len(request) > maxRequestSize {
				return nil, errRequestTooLarge
			}
		}
		if err != nil {
			return request, err
		}
	}
	return request, nil
}

func hasUnsupportedBody(request []byte) bool {
	// Reject request framing that the first proxy does not implement.
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
