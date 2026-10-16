from __future__ import annotations

import http.client
import json
import socket
import threading
from contextlib import contextmanager

import pytest

from shortener.domain import MemoryStore, Shortener
from shortener.http import Application
from shortener.local import create_server, main

CODE = "AbCd0123_-xy"
URL = "https://example.com/docs?ref=demo"


@contextmanager
def running_server(logs):
    app = Application(Shortener(MemoryStore(), clock=lambda: 100, codes=lambda: CODE), logs.append)
    with create_server(0, application=app) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=3)
            assert not thread.is_alive()


@pytest.mark.loopback
def test_real_http_preserves_link_in_process_and_never_fetches_target(capsys):
    logs = []
    with running_server(logs) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        connection.request(
            "POST", "/links", json.dumps({"url": URL}), {"Content-Type": "application/json"}
        )
        created = connection.getresponse()
        assert created.status == 201
        path = json.loads(created.read())["short_path"]
        connection.close()
        for _ in range(2):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 302
            assert response.getheader("Location") == URL
            assert response.getheader("Cache-Control") == "no-store"
            assert response.read() == b""
            connection.close()
    assert len(logs) == 3
    assert all("example.com" not in log and CODE not in log for log in logs)
    assert capsys.readouterr().err == ""
    with running_server([]) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 404  # A new process/store has no previous links.
        response.read()
        connection.close()


@pytest.mark.loopback
@pytest.mark.parametrize(
    "raw_request,expected",
    [
        (b"POST /links HTTP/1.1\r\nHost: local\r\nContent-Length: 4097\r\n\r\n", 413),
        (b"POST /links HTTP/1.1\r\nHost: local\r\nContent-Length: -1\r\n\r\n", 400),
        (
            b"POST /links HTTP/1.1\r\nHost: local\r\n"
            b"Content-Length: 1\r\nContent-Length: 1\r\n\r\nx",
            400,
        ),
        (b"POST /links HTTP/1.1\r\nHost: local\r\nTransfer-Encoding: chunked\r\n\r\n", 415),
        (b"POST //links HTTP/1.1\r\nHost: local\r\n\r\n", 400),
        (b"GET /links?secret=value HTTP/1.1\r\nHost: local\r\n\r\n", 400),
        (b"PUT /links HTTP/1.1\r\nHost: local\r\n\r\n", 405),
        (b"HEAD /links HTTP/1.1\r\nHost: local\r\n\r\n", 405),
        (b"GET /r/../bad HTTP/1.1\r\nHost: local\r\n\r\n", 404),
        (b"POST /links HTTP/1.1\r\nHost: local\r\nExpect: 100-continue\r\n\r\n", 417),
    ],
)
def test_real_http_framing_and_methods_are_bounded(raw_request, expected, capsys):
    logs = []
    with running_server(logs) as port:
        with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
            client.sendall(raw_request)
            response = b""
            while chunk := client.recv(4096):
                response += chunk
            assert int(response.split(b" ", 2)[1]) == expected
            assert b"secret=value" not in response
    assert logs and "secret" not in "".join(logs)
    assert capsys.readouterr().err == ""


def test_cli_safe_argument_errors_and_version(capsys):
    for args in (["--port", "bad\x1b[31m"], ["--port", "80"], ["--unknown\x1b"]):
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
        assert "\x1b" not in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"
