"""Bounded JSON/HTTP contract, shared by REST proxy events and local HTTP."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, NoReturn

from .domain import CODE, InvalidTarget, NotFound, Shortener, StoreUnavailable, has_control

MAX_RAW_BODY = 8192
MAX_BODY = 4096
MAX_PATH = 256
MAX_HEADERS = 32
MAX_HEADER_BYTES = 8192
METHOD = re.compile(r"[A-Z]{1,16}\Z", re.ASCII)
HEADER = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}\Z", re.ASCII)
MESSAGES = {
    "bad_request": "Request does not match the documented HTTP contract.",
    "invalid_url": "URL does not match the documented HTTP(S) target policy.",
    "not_found": "Link not found or expired.",
    "method_not_allowed": "Method is not supported for this route.",
    "payload_too_large": "Request body exceeds the byte limit.",
    "uri_too_long": "Request path exceeds the byte limit.",
    "unsupported_media_type": "Use application/json with UTF-8 and no content encoding.",
    "unavailable": "Service temporarily unavailable.",
    "internal_error": "Request could not be completed.",
}


@dataclass(frozen=True)
class Response:
    status: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def gateway(self) -> dict[str, Any]:
        return {
            "statusCode": self.status,
            "headers": {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                **self.headers,
            },
            "body": self.body,
            "isBase64Encoded": False,
        }


def json_response(status: int, value: object, **headers: str) -> Response:
    return Response(
        status,
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        {"Content-Type": "application/json; charset=utf-8", **headers},
    )


def error(status: int, code: str, **headers: str) -> Response:
    return json_response(status, {"error": {"code": code, "message": MESSAGES[code]}}, **headers)


class Rejected(Exception):
    def __init__(self, response: Response) -> None:
        self.response = response


def reject(status: int = 400, code: str = "bad_request") -> NoReturn:
    raise Rejected(error(status, code))


def validate_headers(pairs: list[tuple[str, str]]) -> dict[str, str]:
    if len(pairs) > MAX_HEADERS:
        reject()
    result: dict[str, str] = {}
    total = 0
    for key, value in pairs:
        if (
            not isinstance(key, str)
            or not isinstance(value, str)
            or len(value) > 2048
            or not HEADER.fullmatch(key)
            or not value.isascii()
            or has_control(value)
        ):
            reject()
        total += len(key) + len(value)
        if total > MAX_HEADER_BYTES or key.lower() in result:
            reject()
        result[key.lower()] = value
    if result.get("content-encoding") is not None or "transfer-encoding" in result:
        reject(415, "unsupported_media_type")
    return result


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def create_payload(body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
    if len(body) > MAX_BODY:
        reject(413, "payload_too_large")
    content_type = headers.get("content-type", "").lower().replace(" ", "")
    if content_type not in ("application/json", "application/json;charset=utf-8"):
        reject(415, "unsupported_media_type")
    try:
        value = json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
        )
    except (ValueError, UnicodeError, RecursionError):
        reject()
    if not isinstance(value, dict) or "url" not in value or set(value) - {"url", "ttl_seconds"}:
        reject()
    return value


class Application:
    def __init__(self, service: Shortener, emit: Callable[[str], None] | None = None) -> None:
        self.service = service
        self.emit = emit

    def handle(
        self, method: str, path: str, headers: list[tuple[str, str]], body: bytes
    ) -> Response:
        route = "unknown"
        try:
            if not METHOD.fullmatch(method) or not path.isascii() or has_control(path):
                reject()
            if len(path) > MAX_PATH:
                reject(414, "uri_too_long")
            if "?" in path or "#" in path or not path.startswith("/"):
                reject()
            clean_headers = validate_headers(headers)
            if len(body) > MAX_BODY:
                reject(413, "payload_too_large")
            if path == "/links":
                route = "create"
                if method != "POST":
                    response = error(405, "method_not_allowed", Allow="POST")
                else:
                    payload = create_payload(body, clean_headers)
                    link = self.service.create(payload["url"], payload.get("ttl_seconds", 86400))
                    short_path = f"/r/{link.code}"
                    response = json_response(
                        201,
                        {
                            "code": link.code,
                            "short_path": short_path,
                            "expires_at": link.expires_at,
                        },
                        Location=f"r/{link.code}",  # Preserve the POST URL's API stage prefix.
                    )
            elif path.startswith("/r/") and CODE.fullmatch(path[3:]):
                route = "redirect"
                if method != "GET":
                    response = error(405, "method_not_allowed", Allow="GET")
                elif body:
                    response = error(400, "bad_request")
                else:
                    response = Response(
                        302, headers={"Location": self.service.resolve(path[3:]).url}
                    )
            else:
                response = error(404, "not_found")
        except Rejected as exc:
            response = exc.response
        except InvalidTarget:
            response = error(400, "invalid_url")
        except ValueError:
            response = error(400, "bad_request")
        except NotFound:
            response = error(404, "not_found")
        except StoreUnavailable:
            response = error(503, "unavailable", **{"Retry-After": "1"})
        except Exception:
            response = error(500, "internal_error")
        self.record(route, response.status)
        return response

    def record(self, route: str, status: int) -> None:
        if self.emit is not None:
            # Only fixed route labels/statuses; never request paths, headers, bodies or exceptions.
            self.emit(json.dumps({"event": "http_result", "route": route, "status": status}))


def gateway_request(event: object) -> tuple[str, str, list[tuple[str, str]], bytes]:
    if not isinstance(event, dict) or event.get("version") is not None:
        reject()  # This adapter supports API Gateway REST proxy v1, not HTTP API v2.
    method, path = event.get("httpMethod"), event.get("path")
    if not isinstance(method, str) or not isinstance(path, str):
        reject()
    for name in ("queryStringParameters", "multiValueQueryStringParameters"):
        query = event.get(name)
        if query is not None and (not isinstance(query, dict) or query):
            reject()
    encoded = event.get("isBase64Encoded")
    body = event.get("body")
    if type(encoded) is not bool or (body is not None and not isinstance(body, str)):
        reject()
    body = body or ""
    try:
        if len(body) > MAX_RAW_BODY or len(body.encode("utf-8")) > MAX_RAW_BODY:
            reject(413, "payload_too_large")
        raw = base64.b64decode(body, validate=True) if encoded else body.encode("utf-8")
    except (ValueError, UnicodeError, binascii.Error):
        reject()
    if len(raw) > MAX_BODY:
        reject(413, "payload_too_large")
    headers = event.get("headers")
    multi = event.get("multiValueHeaders")
    headers = {} if headers is None else headers
    multi = {} if multi is None else multi
    if not isinstance(headers, dict) or not isinstance(multi, dict):
        reject()
    if len(headers) > MAX_HEADERS or len(multi) > MAX_HEADERS:
        reject()
    pairs: list[tuple[str, str]] = []
    # v1 includes the same headers in both maps. Multi-value entries take precedence.
    for key, values in multi.items():
        if not isinstance(key, str) or not isinstance(values, list) or len(values) != 1:
            reject()
        if not isinstance(values[0], str):
            reject()
        pairs.append((key, values[0]))
    multi_names = {key.lower() for key in multi}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            reject()
        if key.lower() in multi_names:
            if any(k.lower() == key.lower() and v != value for k, v in pairs):
                reject()
        else:
            pairs.append((key, value))
    clean_headers = validate_headers(pairs)
    if "content-length" in clean_headers:
        length = clean_headers["content-length"]
        if not re.fullmatch(r"[0-9]{1,6}", length) or int(length) != len(raw):
            reject()
    return method, path, pairs, raw
