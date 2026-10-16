from __future__ import annotations

import base64
import json
from urllib.parse import urljoin

import pytest

from shortener import aws
from shortener.domain import MemoryStore, Shortener, StoreUnavailable
from shortener.http import MAX_BODY, MAX_RAW_BODY, Application, Rejected, gateway_request

URL = "https://example.com/docs?ref=demo"
CODE = "AbCd0123_-xy"
JSON_HEADERS = [("Content-Type", "application/json")]


def app(store=None, emit=None):
    return Application(
        Shortener(store or MemoryStore(), clock=lambda: 100, codes=lambda: CODE), emit
    )


def event(body=None, **kwargs):
    return {
        "httpMethod": "POST",
        "path": "/links",
        "headers": dict(JSON_HEADERS),
        "isBase64Encoded": False,
        "body": json.dumps({"url": URL}) if body is None else body,
        **kwargs,
    }


def test_create_then_redirect_and_default_ttl():
    application = app()
    created = application.handle("POST", "/links", JSON_HEADERS, json.dumps({"url": URL}).encode())
    assert created.status == 201
    assert json.loads(created.body) == {
        "code": CODE,
        "short_path": f"/r/{CODE}",
        "expires_at": 86500,
    }
    assert created.headers["Location"] == f"r/{CODE}"
    redirected = application.handle("GET", f"/r/{CODE}", [], b"")
    assert redirected.status == 302
    assert redirected.headers["Location"] == URL
    assert redirected.body == ""
    assert redirected.gateway()["headers"]["Cache-Control"] == "no-store"
    assert redirected.gateway()["headers"]["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("base", ["https://short.example/demo", "http://127.0.0.1:8000"])
def test_created_location_preserves_service_stage_prefix(base):
    response = app().handle("POST", "/links", JSON_HEADERS, json.dumps({"url": URL}).encode())
    assert urljoin(base + "/links", response.headers["Location"]) == base + f"/r/{CODE}"


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"[]",
        b"null",
        b"true",
        b"1",
        b"NaN",
        b'{"url":"https://example.com","url":"https://evil.example"}',
        b'{"url":"https://example.com","extra":1}',
        b'{"ttl_seconds":10}',
        b'{"url":null}',
        b'{"url":12}',
        b'{"url":[]}',
        b'{"url":true}',
        b'{"url":"https://example.com","ttl_seconds":true}',
        b"[" * 2000,
    ],
    ids=lambda value: repr(value)[:55],
)
def test_malformed_json_and_schema(body):
    response = app().handle("POST", "/links", JSON_HEADERS, body)
    assert response.status == 400
    assert len(response.body) < 300
    assert "evil.example" not in response.body


@pytest.mark.parametrize(
    "content_type",
    [None, "text/plain", "application/json;charset=latin1", "application/json;other=x"],
)
def test_content_type(content_type):
    headers = [] if content_type is None else [("content-type", content_type)]
    assert app().handle("POST", "/links", headers, b"{}").status == 415


def test_utf8_content_type_and_exact_body_bound():
    body = json.dumps({"url": URL}).encode()
    padded = body + b" " * (MAX_BODY - len(body))
    assert (
        app()
        .handle("POST", "/links", [("content-type", "application/json; charset=UTF-8")], padded)
        .status
        == 201
    )
    assert app().handle("POST", "/links", JSON_HEADERS, padded + b" ").status == 413


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"]
)
def test_create_method_restrictions(method):
    response = app().handle(method, "/links", [], b"")
    assert response.status == 405
    assert response.headers["Allow"] == "POST"


@pytest.mark.parametrize("method", ["POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_redirect_method_restrictions(method):
    response = app().handle(method, f"/r/{CODE}", [], b"")
    assert response.status == 405
    assert response.headers["Allow"] == "GET"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/admin",
        "/links/",
        "/r/",
        "/r/../links",
        f"/r/{CODE}/",
        "/r/" + "a" * 11,
        "/r/" + "%41" * 12,
        "//links",
    ],
)
def test_route_grammar(path):
    assert app().handle("GET", path, [], b"").status == 404


@pytest.mark.parametrize(
    "path", ["links", "/links?x=secret", "/links#fragment", "/\x1b[31m", "/雪"]
)
def test_bad_paths(path):
    assert app().handle("POST", path, JSON_HEADERS, b"{}").status == 400


def test_path_size_and_missing_or_expired_are_404():
    assert app().handle("GET", "/" + "a" * 256, [], b"").status == 414
    assert app().handle("GET", f"/r/{CODE}", [], b"").status == 404
    assert app().handle("GET", f"/r/{CODE}", [], b"x").status == 400


@pytest.mark.parametrize(
    "headers",
    [
        [("content-type", "application/json"), ("Content-Type", "text/plain")],
        [("X", "secret\r\nInjected: yes")],
        [("bad header", "x")],
        [("X", "\x1b")],
        [("X", "x" * 2049)],
        [(f"X-{i}", "x") for i in range(33)],
        [("Transfer-Encoding", "chunked")],
        [("Content-Encoding", "gzip")],
    ],
)
def test_header_rejection(headers):
    assert app().handle("POST", "/links", headers, b"{}").status in (400, 415)


def test_safe_error_and_logs_exclude_targets_queries_request_data_and_exceptions():
    logs = []

    class BrokenStore:
        def insert(self, link):
            raise StoreUnavailable("secret-target?token=sensitive\x1b[31m")

        def get(self, code):
            raise StoreUnavailable("secret-target?token=sensitive")

    application = app(BrokenStore(), logs.append)
    response = application.handle("POST", "/links", JSON_HEADERS, json.dumps({"url": URL}).encode())
    assert response.status == 503
    assert response.headers["Retry-After"] == "1"
    assert application.handle("GET", f"/r/{CODE}", [], b"").status == 503
    assert application.handle("GET", "/bad?token=sensitive", [], b"").status == 400
    assert logs == [
        '{"event": "http_result", "route": "create", "status": 503}',
        '{"event": "http_result", "route": "redirect", "status": 503}',
        '{"event": "http_result", "route": "unknown", "status": 400}',
    ]
    for raw in [response.body, *logs]:
        assert not any(
            value in raw for value in ("example.com", "sensitive", "secret", "\x1b", CODE)
        )


def test_gateway_accepts_plain_base64_and_multivalue_headers_without_double_decode():
    plain = event()
    encoded = event(base64.b64encode(plain["body"].encode()).decode(), isBase64Encoded=True)
    assert gateway_request(plain) == gateway_request(encoded)
    plain["multiValueHeaders"] = {"Content-Type": ["application/json"]}
    assert gateway_request(plain)[2] == JSON_HEADERS


@pytest.mark.parametrize(
    "patch",
    [
        {"httpMethod": None},
        {"path": []},
        {"version": "2.0"},
        {"body": {}},
        {"body": "\ud800"},
        {"isBase64Encoded": "true"},
        {"isBase64Encoded": None},
        {"isBase64Encoded": True, "body": "!!!!"},
        {"isBase64Encoded": True, "body": "e30"},
        {"isBase64Encoded": True, "body": "雪"},
        {"headers": []},
        {"headers": {"x": 1}},
        {"multiValueHeaders": []},
        {"multiValueHeaders": {"x": ["a", "b"]}},
        {"multiValueHeaders": {"x": "value"}},
        {"multiValueHeaders": {"x": [1]}},
        {"multiValueHeaders": {"Content-Type": ["text/plain"]}},
        {"queryStringParameters": {"token": "sensitive"}},
        {"queryStringParameters": []},
    ],
)
def test_gateway_malformed_envelopes(patch):
    with pytest.raises(Rejected):
        gateway_request(event(**patch))


@pytest.mark.parametrize("value", [None, [], "event", {}])
def test_gateway_non_events(value):
    with pytest.raises(Rejected):
        gateway_request(value)


def test_gateway_raw_decoded_limits():
    for body, encoded in [
        ("a" * (MAX_RAW_BODY + 1), True),
        ("a" * (MAX_BODY + 1), False),
        (base64.b64encode(b"a" * (MAX_BODY + 1)).decode(), True),
    ]:
        with pytest.raises(Rejected) as exc:
            gateway_request(event(body, isBase64Encoded=encoded))
        assert exc.value.response.status == 413
    assert len(gateway_request(event("a" * MAX_BODY))[3]) == MAX_BODY
    assert (
        len(
            gateway_request(
                event(base64.b64encode(b"a" * MAX_BODY).decode(), isBase64Encoded=True)
            )[3]
        )
        == MAX_BODY
    )


@pytest.mark.parametrize(
    "headers",
    [
        {f"X-{index}": "x" for index in range(33)},
        {"Content-Length": "1"},
        {"Content-Length": "-1"},
        {"Content-Length": "9" * 2048},
        {"X": "x" * 2049},
    ],
)
def test_gateway_header_and_content_length_limits(headers):
    with pytest.raises(Rejected):
        gateway_request(event(headers=headers))


def test_gateway_accepts_matching_content_length_for_base64():
    body = json.dumps({"url": URL}).encode()
    encoded = event(
        base64.b64encode(body).decode(),
        isBase64Encoded=True,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    assert gateway_request(encoded)[3] == body


def test_lambda_entrypoint_with_injected_application_and_sanitized_init_failure(
    monkeypatch, capsys
):
    monkeypatch.setattr(aws, "_application", app())
    result = aws.lambda_handler(event(), None)
    assert result["statusCode"] == 201
    assert (
        aws.lambda_handler(event("", httpMethod="GET", path=f"/r/{CODE}"), None)["headers"][
            "Location"
        ]
        == URL
    )
    monkeypatch.setattr(aws, "_application", None)

    def fail():
        raise RuntimeError("sensitive credential internal")

    monkeypatch.setattr(aws, "make_application", fail)
    assert aws.lambda_handler(event(), None)["statusCode"] == 503
    assert "sensitive" not in capsys.readouterr().out
    assert aws.lambda_handler({}, None)["statusCode"] == 400


def test_unknown_store_exception_is_safe_500():
    class UnexpectedStore:
        def insert(self, link):
            raise RuntimeError("secret")

        def get(self, code):
            raise RuntimeError("secret")

    response = app(UnexpectedStore()).handle(
        "POST", "/links", JSON_HEADERS, json.dumps({"url": URL}).encode()
    )
    assert response.status == 500
    assert "secret" not in response.body
