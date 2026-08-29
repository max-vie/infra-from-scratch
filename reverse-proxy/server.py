import argparse
import socket


# Keep the first proxy local and point it at the existing HTTP server.
DEFAULT_LISTEN_ADDRESS = ("127.0.0.1", 8080)
DEFAULT_BACKEND_ADDRESS = ("127.0.0.1", 8088)
BUFFER_SIZE = 4096
MAX_REQUEST_SIZE = 64 * 1024
SOCKET_TIMEOUT = 5
UNSUPPORTED_BODY_HEADERS = {b"content-length", b"transfer-encoding"}


def port(value):
    # Validate command-line port values.
    value = int(value)
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return value


def read_request(connection):
    # Read one header-terminated request with a bounded buffer.
    request = bytearray()
    while b"\r\n\r\n" not in request:
        chunk = connection.recv(BUFFER_SIZE)
        if not chunk:
            break
        request.extend(chunk)
        if len(request) > MAX_REQUEST_SIZE:
            raise ValueError("request headers are too large")
    return bytes(request)


def has_unsupported_body(request):
    # Reject request framing that the first proxy does not implement.
    header_lines = request.split(b"\r\n\r\n", 1)[0].split(b"\r\n")[1:]
    return any(
        line.split(b":", 1)[0].strip().lower() in UNSUPPORTED_BODY_HEADERS
        for line in header_lines
    )


def send_error(connection, status, body):
    # Send an HTTP/1.0 error response and close the connection afterward.
    response = (
        f"HTTP/1.0 {status}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body
    connection.sendall(response)


def handle_connection(client, backend_address):
    # Read the request before opening the backend connection.
    client.settimeout(SOCKET_TIMEOUT)

    try:
        request = read_request(client)
    except (OSError, ValueError):
        # Reject malformed or incomplete requests.
        try:
            send_error(client, "400 Bad Request", b"Bad Request\n")
        except OSError:
            pass
        return

    if not request:
        try:
            send_error(client, "400 Bad Request", b"Bad Request\n")
        except OSError:
            pass
        return
    if b"\r\n\r\n" not in request:
        # Reject a connection that closes before sending complete headers.
        try:
            send_error(client, "400 Bad Request", b"Bad Request\n")
        except OSError:
            pass
        return
    if has_unsupported_body(request):
        try:
            send_error(client, "400 Bad Request", b"Bad Request\n")
        except OSError:
            pass
        return

    response_started = False
    try:
        # Forward the raw request and relay the backend response.
        with socket.create_connection(backend_address, timeout=SOCKET_TIMEOUT) as backend:
            backend.sendall(request)
            backend.shutdown(socket.SHUT_WR)

            while chunk := backend.recv(BUFFER_SIZE):
                response_started = True
                client.sendall(chunk)
    except OSError:
        # Report an unavailable or failed backend to the client.
        if response_started:
            return
        try:
            send_error(client, "502 Bad Gateway", b"Bad Gateway\n")
        except OSError:
            pass


def serve(listen_address=DEFAULT_LISTEN_ADDRESS, backend_address=DEFAULT_BACKEND_ADDRESS):
    # Listen for local TCP connections.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(listen_address)
        listener.listen(1)
        print(
            f"serving reverse proxy on {listen_address[0]}:{listen_address[1]} "
            f"to {backend_address[0]}:{backend_address[1]}"
        )

        # Handle one client connection at a time.
        while True:
            client, _ = listener.accept()
            with client:
                handle_connection(client, backend_address)


def parse_args(argv=None):
    # Keep listener and backend addresses configurable for local experiments.
    parser = argparse.ArgumentParser(description="Forward HTTP requests to one backend")
    parser.add_argument("--listen-host", default=DEFAULT_LISTEN_ADDRESS[0])
    parser.add_argument("--listen-port", type=port, default=DEFAULT_LISTEN_ADDRESS[1])
    parser.add_argument("--backend-host", default=DEFAULT_BACKEND_ADDRESS[0])
    parser.add_argument("--backend-port", type=port, default=DEFAULT_BACKEND_ADDRESS[1])
    return parser.parse_args(argv)


def main(argv=None):
    # Parse command-line options and start the proxy.
    args = parse_args(argv)
    serve(
        listen_address=(args.listen_host, args.listen_port),
        backend_address=(args.backend_host, args.backend_port),
    )


if __name__ == "__main__":
    main()
