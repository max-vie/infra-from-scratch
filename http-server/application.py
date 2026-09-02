from dataclasses import dataclass


@dataclass(frozen=True)
class Request:
    method: str
    target: str


@dataclass(frozen=True)
class Response:
    status: str
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


ROUTES = {
    "/": ("200 OK", b"HELLO WORLD!\n"),
    "/health": ("200 OK", b"OK\n"),
    "/hello": ("200 OK", b"HELLO WORLD!\n"),
}


def respond(request):
    if request.method != "GET":
        return Response(
            "405 Method Not Allowed",
            b"Method Not Allowed\n",
            (("Allow", "GET"),),
        )

    status, body = ROUTES.get(request.target, ("404 Not Found", b"Not Found\n"))
    return Response(status, body)
