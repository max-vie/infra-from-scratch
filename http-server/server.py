import socket


# Bind on all local interfaces so the server can accept local or LAN requests.
HOST, PORT = "", 8088

listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# Allow the server to restart without waiting for the old socket to expire.
listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listen_socket.bind((HOST, PORT))
listen_socket.listen(1)
print(f"serving HTTP on port {PORT} ...")

while True:
    # Wait for the next client connection.
    client_connection, client_address = listen_socket.accept()
    with client_connection:
        # Read the beginning of the client's HTTP request for demonstration.
        request_data = client_connection.recv(1024)
        print(request_data.decode("utf-8", errors="replace"))

        response_body = b"HELLO WORLD!\n"
        # HTTP headers use CRLF line endings; Content-Length frames the body.
        http_response = (
            b"HTTP/1.1 200 OK\r\n"
            + f"Content-Length: {len(response_body)}\r\n".encode("ascii")
            + b"Connection: close\r\n"
            + b"\r\n"
            + response_body
        )

        client_connection.sendall(http_response)
