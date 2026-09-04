import socket
import sys
from dataclasses import dataclass


SUPPORTED_VERSIONS = {"HTTP/1.0", "HTTP/1.1"}
TOKEN_SYMBOLS = "!#$%&'*+-.^_`|~"


@dataclass
class Response:
    version: str
    status: int
    reason: str
    headers: dict[str, str]
    body: bytes


def _is_token(value):
    return bool(value) and value.isascii() and all(
        character.isalnum() or character in TOKEN_SYMBOLS for character in value
    )


def _decode_line(line):
    if not line.endswith(b"\r\n"):
        raise ValueError("incomplete response line")
    return line[:-2].decode("iso-8859-1")


def _read_response(response_file):
    status_line = response_file.readline()
    if not status_line:
        raise ValueError("empty HTTP response")

    status_line = _decode_line(status_line)
    try:
        version, raw_status, reason = status_line.split(" ", 2)
    except ValueError:
        raise ValueError("malformed response status line") from None
    if (
        version not in SUPPORTED_VERSIONS
        or len(raw_status) != 3
        or not raw_status.isascii()
        or not raw_status.isdigit()
    ):
        raise ValueError("malformed response status line")
    if any(
        (ord(character) < 32 and character != "\t")
        or ord(character) == 127
        for character in reason
    ):
        raise ValueError("malformed response reason phrase")

    headers = {}
    while True:
        line = response_file.readline()
        if not line:
            raise ValueError("incomplete response headers")
        if line == b"\r\n":
            break

        header_line = _decode_line(line)
        try:
            name, value = header_line.split(":", 1)
        except ValueError:
            raise ValueError("malformed response header") from None
        name = name.casefold()
        if not _is_token(name):
            raise ValueError("malformed response header name")
        if any(
            (ord(character) < 32 and character != "\t")
            or ord(character) == 127
            for character in value
        ):
            raise ValueError("malformed response header value")
        headers[name] = value.strip(" \t")

    if "transfer-encoding" in headers:
        raise NotImplementedError("Transfer-Encoding responses are not supported")
    if "content-encoding" in headers:
        raise NotImplementedError("Content-Encoding responses are not supported")

    return Response(
        version=version,
        status=int(raw_status),
        reason=reason,
        headers=headers,
        body=response_file.read(),
    )

# Parse the scheme, host, and request path for the HTTP client.
class URL:
    def __init__(self, address):
        # Treat a bare host or host:port as an HTTP address.
        if "://" not in address:
            address = "http://" + address

        self.scheme, address = address.split("://", 1)
        if self.scheme != "http":
            raise ValueError("Only http:// addresses are supported") # for now :^)

        if "/" in address:
            authority, path = address.split("/", 1)
            self.path = "/" + path
        else:
            authority = address
            self.path = "/"

        if ":" in authority:
            self.host, port = authority.rsplit(":", 1)
            try:
                self.port = int(port)
            except ValueError as error:
                raise ValueError(f"Invalid port in {address!r}") from error
        else:
            self.host = authority
            self.port = 80

        if not self.host:
            raise ValueError("A host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")

        self.host_header = authority

    def request(self):
        # Open a TCP connection and send the existing HTTP/1.0 request.
        with socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        ) as s:
            s.connect((self.host, self.port))

            request = "GET {} HTTP/1.0\r\n".format(self.path)
            request += "Host: {}\r\n".format(self.host_header)
            request += "\r\n"
            s.sendall(request.encode("utf8"))

            # Read response metadata as text and preserve the body as bytes.
            with s.makefile("rb") as response:
                return _read_response(response)

# Run one HTTP request when this file is executed from the command line.
if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python client.py [http://]host[:port][/path]")

    response = URL(sys.argv[1]).request()
    sys.stdout.buffer.write(response.body)
