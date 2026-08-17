import socket
import sys

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

            # Read the status line, headers, and response body.
            with s.makefile("r", encoding="utf8", newline="\r\n") as response:
                statusline = response.readline()
                if not statusline:
                    return ""

                version, status, explanation = statusline.split(" ", 2)
                response_headers = {}
                while True:
                    line = response.readline()
                    if line in {"\r\n", ""}:
                        break
                    header, value = line.split(":", 1)
                    response_headers[header.casefold()] = value.strip()

                # Reject encodings this minimal client cannot frame or decode safely.
                if "transfer-encoding" in response_headers:
                    raise NotImplementedError(
                        "Transfer-Encoding responses are not supported"
                    )
                if "content-encoding" in response_headers:
                    raise NotImplementedError(
                        "Content-Encoding responses are not supported"
                    )
                return response.read()

# Run one HTTP request when this file is executed from the command line.
if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python client.py [http://]host[:port][/path]")

    print(URL(sys.argv[1]).request())
