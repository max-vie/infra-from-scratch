import argparse
import socket


DEFAULT_LISTEN_ADDRESS = ("127.0.0.1", 8000)
BACKEND_COUNT = 2
BUFFER_SIZE = 4096
MAX_REQUEST_SIZE = 64 * 1024
SOCKET_TIMEOUT = 5
UNSUPPORTED_BODY_HEADERS = {b"content-length", b"transfer-encoding"}


def port(value):
    try:
        value = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer") from None
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return value


def backend(value):
    try:
        host, raw_port = value.rsplit(":", 1)
        if not host or not raw_port:
            raise ValueError
        return host, port(raw_port)
    except (ValueError, argparse.ArgumentTypeError):
        raise argparse.ArgumentTypeError("backend must be HOST:PORT") from None


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

    header_end = request.find(b"\r\n\r\n")
    if header_end == -1:
        return bytes(request)
    header_end += 4
    if header_end > MAX_REQUEST_SIZE:
        raise ValueError("request headers are too large")
    return bytes(request[:header_end])


def has_unsupported_body(request):
    # Reject request framing that this first load balancer does not implement.
    header_lines = request.split(b"\r\n\r\n", 1)[0].split(b"\r\n")[1:]
    return any(
        line.split(b":", 1)[0].strip().lower() in UNSUPPORTED_BODY_HEADERS
        for line in header_lines
    )


def send_error(connection, status, body):
    response = (
        f"HTTP/1.0 {status}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body
    try:
        connection.sendall(response)
    except OSError:
        pass


def handle_connection(client, backend_addresses, backend_index):
    # Validate the request before choosing a backend.
    client.settimeout(SOCKET_TIMEOUT)
    try:
        request = read_request(client)
        if (
            not request
            or b"\r\n\r\n" not in request
            or has_unsupported_body(request)
        ):
            raise ValueError("unsupported request")
    except (OSError, ValueError):
        send_error(client, "400 Bad Request", b"Bad Request\n")
        return backend_index

    initial_index = backend_index
    next_backend_index = (initial_index + 1) % len(backend_addresses)
    for offset in range(len(backend_addresses)):
        selected_backend = backend_addresses[(initial_index + offset) % len(backend_addresses)]
        response_started = False
        try:
            # Forward the request and relay the response until the backend closes.
            with socket.create_connection(
                selected_backend,
                timeout=SOCKET_TIMEOUT,
            ) as backend_connection:
                backend_connection.sendall(request)
                backend_connection.shutdown(socket.SHUT_WR)

                while chunk := backend_connection.recv(BUFFER_SIZE):
                    response_started = True
                    client.sendall(chunk)
            return next_backend_index
        except OSError:
            if response_started:
                # Response bytes already reached the client; do not retry
                # or append another error.
                return next_backend_index
            if offset == len(backend_addresses) - 1:
                send_error(client, "502 Bad Gateway", b"Bad Gateway\n")

    return next_backend_index


def validate_backends(backend_addresses):
    if len(backend_addresses) != BACKEND_COUNT:
        raise ValueError("exactly two backends are required")


def serve(
    listen_address=DEFAULT_LISTEN_ADDRESS,
    backend_addresses=(),
):
    backend_addresses = tuple(backend_addresses)
    validate_backends(backend_addresses)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(listen_address)
        listener.listen(1)
        print(
            f"serving load balancer on {listen_address[0]}:{listen_address[1]} "
            f"with {len(backend_addresses)} backends"
        )

        backend_index = 0
        while True:
            client, _ = listener.accept()
            with client:
                backend_index = handle_connection(
                    client,
                    backend_addresses,
                    backend_index,
                )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Forward HTTP requests between two backends"
    )
    parser.add_argument("--listen-host", default=DEFAULT_LISTEN_ADDRESS[0])
    parser.add_argument("--listen-port", type=port, default=DEFAULT_LISTEN_ADDRESS[1])
    parser.add_argument(
        "--backend",
        dest="backend_addresses",
        metavar="HOST:PORT",
        type=backend,
        action="append",
        required=True,
    )
    args = parser.parse_args(argv)
    if len(args.backend_addresses) != BACKEND_COUNT:
        parser.error("exactly two --backend options are required")
    return args


def main(argv=None):
    args = parse_args(argv)
    serve(
        listen_address=(args.listen_host, args.listen_port),
        backend_addresses=args.backend_addresses,
    )


if __name__ == "__main__":
    main()
