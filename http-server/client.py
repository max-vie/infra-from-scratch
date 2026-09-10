import socket
import struct
import sys
from dataclasses import dataclass


SUPPORTED_VERSIONS = {"HTTP/1.0", "HTTP/1.1"}
TOKEN_SYMBOLS = "!#$%&'*+-.^_`|~"
DNS_HEADER_SIZE = 12
DNS_TYPE_A = 1
DNS_CLASS_IN = 1


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


def _encode_dns_name(host):
    labels = host.rstrip(".").split(".")
    if not host or any(not label for label in labels):
        raise ValueError("Invalid DNS name")

    encoded = bytearray()
    for label in labels:
        try:
            label_bytes = label.encode("ascii")
        except UnicodeEncodeError as error:
            raise ValueError("DNS names must use ASCII labels") from error
        if len(label_bytes) > 63:
            raise ValueError("DNS labels are limited to 63 bytes")
        encoded.append(len(label_bytes))
        encoded.extend(label_bytes)
    encoded.append(0)
    return bytes(encoded)


def _build_dns_query(host, transaction_id):
    header = struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
    question = _encode_dns_name(host) + struct.pack(
        "!HH", DNS_TYPE_A, DNS_CLASS_IN
    )
    return header + question


def _skip_dns_name(packet, position):
    while True:
        if position >= len(packet):
            raise ValueError("truncated DNS name")
        length = packet[position]
        if length == 0:
            return position + 1
        if length & 0xC0 == 0xC0:
            if position + 2 > len(packet):
                raise ValueError("truncated DNS pointer")
            return position + 2
        if length & 0xC0:
            raise ValueError("invalid DNS label")
        position += 1
        if position + length > len(packet):
            raise ValueError("truncated DNS label")
        position += length


def _parse_dns_address(packet, transaction_id):
    if len(packet) < DNS_HEADER_SIZE:
        raise ValueError("truncated DNS response")

    response_id, flags, question_count, answer_count, _, _ = struct.unpack(
        "!HHHHHH", packet[:DNS_HEADER_SIZE]
    )
    if response_id != transaction_id:
        raise ValueError("unexpected DNS transaction ID")
    if not flags & 0x8000 or flags & 0x000F:
        raise ValueError("DNS response was not successful")
    if question_count != 1:
        raise ValueError("DNS response did not contain one question")

    position = _skip_dns_name(packet, DNS_HEADER_SIZE)
    if position + 4 > len(packet):
        raise ValueError("truncated DNS question")
    position += 4

    for _ in range(answer_count):
        position = _skip_dns_name(packet, position)
        if position + 10 > len(packet):
            raise ValueError("truncated DNS answer")
        record_type, record_class, _, data_length = struct.unpack(
            "!HHIH", packet[position:position + 10]
        )
        position += 10
        if position + data_length > len(packet):
            raise ValueError("truncated DNS answer data")
        if (
            record_type == DNS_TYPE_A
            and record_class == DNS_CLASS_IN
            and data_length == 4
        ):
            return socket.inet_ntoa(packet[position:position + data_length])
        position += data_length

    raise ValueError("DNS response did not contain an IPv4 address")


class DNSResolver:
    def __init__(self, nameserver, timeout=0.1):
        self.nameserver = nameserver
        self.timeout = timeout

    def resolve(self, host):
        transaction_id = 0x1234
        query = _build_dns_query(host, transaction_id)
        with socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
            proto=socket.IPPROTO_UDP,
        ) as query_socket:
            query_socket.settimeout(self.timeout)
            query_socket.sendto(query, self.nameserver)
            response, _ = query_socket.recvfrom(512)
        return _parse_dns_address(response, transaction_id)

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

    def request(self, resolver=None):
        # Open a TCP connection and send the existing HTTP/1.0 request.
        host = resolver.resolve(self.host) if resolver else self.host
        with socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        ) as s:
            s.connect((host, self.port))

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
