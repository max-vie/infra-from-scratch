import argparse
import socket


# Bind on all IPv4 interfaces so the server can accept local or LAN requests.
HOST, PORT = "0.0.0.0", 8088
BUFFER_SIZE = 4096
MAX_REQUEST_SIZE = 64 * 1024
SUPPORTED_VERSIONS = {"HTTP/1.0", "HTTP/1.1"}
TOKEN_SYMBOLS = "!#$%&'*+-.^_`|~"
ROUTES = {
    "/": ("200 OK", b"HELLO WORLD!\n"),
    "/health": ("200 OK", b"OK\n"),
    "/hello": ("200 OK", b"HELLO WORLD!\n"),
}


def port(value):
    value = int(value)
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return value


def _is_token(value):
    return bool(value) and value.isascii() and all(
        character.isalnum() or character in TOKEN_SYMBOLS for character in value
    )


def parse_request_line(line):
    # Parse the method, target, and HTTP version from one request line.
    try:
        method, target, version = line.decode("ascii").split(" ")
    except (UnicodeDecodeError, ValueError):
        raise ValueError("malformed request line") from None

    if (
        not _is_token(method)
        or not target.startswith("/")
        or any(ord(character) < 32 or ord(character) == 127 for character in target)
        or version not in SUPPORTED_VERSIONS
    ):
        raise ValueError("malformed request line")
    return method, target, version


def parse_headers(header_block):
    # Parse CRLF-separated headers into a case-insensitive mapping.
    headers = {}
    for line in header_block.split(b"\r\n") if header_block else ():
        try:
            name, value = line.decode("iso-8859-1").split(":", 1)
        except ValueError:
            raise ValueError("malformed header") from None

        name = name.casefold()
        if not _is_token(name) or name in headers:
            raise ValueError("malformed header name")
        if any(
            (ord(character) < 32 and character != "\t") or ord(character) == 127
            for character in value
        ):
            raise ValueError("malformed header value")
        headers[name] = value.strip(" \t")
    return headers


def parse_request(request):
    # Split the header block before parsing its request line and fields.
    header_block, separator, _ = request.partition(b"\r\n\r\n")
    if not separator:
        raise ValueError("incomplete request headers")

    request_line, *header_lines = header_block.split(b"\r\n")
    if not request_line:
        raise ValueError("missing request line")
    return (
        *parse_request_line(request_line),
        parse_headers(b"\r\n".join(header_lines)),
    )


def read_request(connection):
    # Read until the complete header block arrives, with a bounded buffer.
    request = bytearray()
    while b"\r\n\r\n" not in request:
        chunk = connection.recv(BUFFER_SIZE)
        if not chunk:
            raise ValueError("incomplete request headers")
        request.extend(chunk)
        if len(request) > MAX_REQUEST_SIZE:
            raise ValueError("request headers are too large")

    header_end = request.find(b"\r\n\r\n") + 4
    if header_end > MAX_REQUEST_SIZE:
        raise ValueError("request headers are too large")
    return bytes(request[:header_end])


def route(method, target):
    # Select the small set of routes supported by this MVP.
    if method != "GET":
        return "405 Method Not Allowed", b"Method Not Allowed\n", (("Allow", "GET"),)
    status, body = ROUTES.get(target, ("404 Not Found", b"Not Found\n"))
    return status, body, ()


def build_response(status, body, headers=()):
    # Construct a close-delimited HTTP response with an explicit body length.
    response_headers = [
        f"HTTP/1.1 {status}",
        *(f"{name}: {value}" for name, value in headers),
        f"Content-Length: {len(body)}",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(response_headers).encode("ascii") + body


def handle_connection(connection):
    # Parse one request and prepare exactly one response.
    try:
        method, target, _version, headers = parse_request(read_request(connection))
        if {"content-length", "transfer-encoding"} & headers.keys():
            raise ValueError("request bodies are not supported")
        response = build_response(*route(method, target))
    except (OSError, ValueError):
        response = build_response("400 Bad Request", b"Bad Request\n")

    try:
        connection.sendall(response)
    except OSError:
        pass


def serve(host=HOST, port=PORT):
    # Listen for one request per connection.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listen_socket:
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind((host, port))
        listen_socket.listen(1)
        print(f"serving HTTP on {host}:{port} ...")

        while True:
            client_connection, _ = listen_socket.accept()
            with client_connection:
                handle_connection(client_connection)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Serve the minimal HTTP application")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=port, default=PORT)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
