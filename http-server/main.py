import socket


# Parse the scheme, host, and request path for the HTTP client.
class URL:
    def __init__(self, url):
        self.scheme, url = url.split("://", 1)

        assert self.scheme == "http"

        if "/" not in url:
            url = url + "/"

        self.host, url = url.split("/", 1)
        self.path = "/" + url

    def request(self):
        # Open a TCP connection and send the existing HTTP/1.0 request.
        with socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        ) as s:
            s.connect((self.host, 80))

            request = "GET {} HTTP/1.0\r\n".format(self.path)
            request += "Host: {}\r\n".format(self.host)
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

                # TODO: replace assertions with explicit response handling.
                assert "transfer-encoding" not in response_headers
                assert "content-encoding" not in response_headers
                return response.read()
