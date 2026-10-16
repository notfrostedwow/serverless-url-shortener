"""Loopback-only real HTTP server with explicitly nonpersistent bounded storage."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, NoReturn

from . import __version__
from .domain import MemoryStore, Shortener
from .http import MAX_BODY, Application, Rejected, Response, error, validate_headers


def handler_for(application: Application) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.0 and Connection: close prevent unread/oversize body request reuse.
        server_version = "LocalShortener"
        sys_version = ""
        timeout = 3
        raw_requestline: bytes

        def log_message(self, format: str, *args: Any) -> None:
            pass  # The stdlib default logs request targets, which can contain PII.

        def send_error(
            self, code: int, message: str | None = None, explain: str | None = None
        ) -> None:
            del message, explain
            # BaseHTTPRequestHandler also rejects malformed/oversize HTTP framing.
            self.respond(error(code, "bad_request"))
            application.record("unknown", code)

        def respond(self, response: Response) -> None:
            data = response.body.encode("utf-8")
            self.send_response(response.status)
            for key, value in response.gateway()["headers"].items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def dispatch(self) -> None:
            try:
                parts = self.raw_requestline.rstrip(b"\r\n").split(b" ")
                if len(parts) != 3 or parts[1] != self.path.encode("ascii"):
                    raise Rejected(error(400, "bad_request"))
                pairs = list(self.headers.items())
                headers = validate_headers(pairs)
                length = headers.get("content-length", "0")
                if not length.isascii() or not length.isdecimal() or len(length) > 6:
                    raise Rejected(error(400, "bad_request"))
                size = int(length)
                if size > MAX_BODY:
                    raise Rejected(error(413, "payload_too_large"))
                if "expect" in headers:
                    raise Rejected(error(417, "bad_request"))
                body = self.rfile.read(size)
                if len(body) != size:
                    raise Rejected(error(400, "bad_request"))
                response = application.handle(self.command, self.path, pairs, body)
            except Rejected as exc:
                response = exc.response
                application.record("unknown", response.status)
            except TimeoutError:
                response = error(408, "bad_request")
                application.record("unknown", 408)
            except UnicodeError:
                response = error(400, "bad_request")
                application.record("unknown", 400)
            self.respond(response)

        do_POST = dispatch
        do_GET = dispatch
        do_HEAD = dispatch
        do_PUT = dispatch
        do_DELETE = dispatch
        do_PATCH = dispatch
        do_OPTIONS = dispatch
        do_TRACE = dispatch
        do_CONNECT = dispatch

    return Handler


def create_server(
    port: int = 8000,
    *,
    application: Application | None = None,
    emit: Callable[[str], None] | None = print,
) -> HTTPServer:
    app = application or Application(Shortener(MemoryStore()), emit)

    class LocalServer(HTTPServer):
        def handle_error(self, request: object, client_address: object) -> None:
            del request, client_address
            app.record("unknown", 500)

    return LocalServer(("127.0.0.1", port), handler_for(app))


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        self.exit(2, "error: invalid arguments; use --help\n")


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description="Loopback URL shortener; in-memory links last until process exit")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("invalid port")
    try:
        with create_server(args.port) as server:
            print(
                json.dumps(
                    {
                        "event": "local_server_started",
                        "address": f"http://127.0.0.1:{args.port}",
                        "storage": "memory_only",
                        "authentication": "none_local_demo",
                        "capacity": 1000,
                    }
                ),
                flush=True,
            )
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    except OSError:
        print("error: local HTTP server unavailable", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
