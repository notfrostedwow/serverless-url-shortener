"""Typed domain model, conservative URL policy and injected application service."""

from __future__ import annotations

import ipaddress
import re
import secrets
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Protocol
from urllib.parse import quote, unquote_to_bytes, urlsplit

CODE = re.compile(r"[A-Za-z0-9_-]{12}\Z", re.ASCII)
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)
BAD_PERCENT = re.compile(r"%(?![0-9a-fA-F]{2})")
MAX_URL_BYTES = 2048
MAX_TTL = 604_800
DEFAULT_TTL = 86_400
MAX_COLLISIONS = 5


class InvalidTarget(ValueError):
    """The target does not satisfy the documented URL policy."""


class StoreUnavailable(Exception):
    """Storage failed or reached its explicit capacity."""


class NotFound(Exception):
    """The code is absent or has expired."""


def has_control(value: str) -> bool:
    return any(unicodedata.category(char).startswith("C") for char in value)


def target_url(value: object) -> str:
    """Produce an ASCII Location without decoding or rewriting existing query escapes.

    Hostnames must already be ASCII DNS names (valid IDNA A-labels allowed) or IP
    literals. Unicode path/query/fragment text is UTF-8 percent-encoded. Escapes
    must decode once to valid UTF-8 without controls/backslashes; never double-decode.
    No DNS or HTTP request is performed.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_URL_BYTES:
        raise InvalidTarget
    if has_control(value) or any(char.isspace() for char in value) or "\\" in value:
        raise InvalidTarget
    if len(value.encode("utf-8")) > MAX_URL_BYTES or BAD_PERCENT.search(value):
        raise InvalidTarget
    try:
        decoded = unquote_to_bytes(value).decode("utf-8")
        if has_control(decoded) or "\\" in decoded:
            raise InvalidTarget
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or "@" in parsed.netloc:
            raise InvalidTarget
        host = parsed.hostname
        if not host or not host.isascii() or "%" in host or parsed.netloc.endswith(":"):
            raise InvalidTarget
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise InvalidTarget
        if ":" in host:
            normalized_host = f"[{ipaddress.IPv6Address(host).compressed}]"
            # urlsplit otherwise tolerates junk following a closing IPv6 bracket.
            if not re.fullmatch(r"\[[0-9a-fA-F:.]+\](?::[0-9]+)?", parsed.netloc):
                raise InvalidTarget
        else:
            try:
                normalized_host = str(ipaddress.IPv4Address(host))
            except ValueError:
                labels = host.split(".")
                if (
                    len(host) > 253
                    or len(labels) < 2
                    or not labels[-1][0:1].isalpha()
                    or any(not LABEL.fullmatch(label) for label in labels)
                ):
                    raise InvalidTarget from None
                for label in labels:
                    if (
                        label.startswith("xn--")
                        and label.encode("ascii").decode("idna").encode("idna").decode("ascii")
                        != label
                    ):
                        raise InvalidTarget from None
                normalized_host = host
        authority = normalized_host + (f":{port}" if port is not None else "")
        safe = "/:@!$&'()*+,;=-._~%"
        tail = quote(parsed.path, safe=safe)
        if "?" in value.split("#", 1)[0]:
            tail += "?" + quote(parsed.query, safe=safe + "?")
        if "#" in value:
            tail += "#" + quote(parsed.fragment, safe=safe + "?")
        result = f"{parsed.scheme}://{authority}{tail}"
        if len(result) > MAX_URL_BYTES:
            raise InvalidTarget
        return result
    except (ValueError, UnicodeError) as exc:
        raise InvalidTarget from exc


@dataclass(frozen=True)
class Link:
    code: str
    url: str
    created_at: int
    expires_at: int


class Store(Protocol):
    def insert(self, link: Link) -> bool:
        """Atomically insert if absent; False means collision, never overwrite."""

    def get(self, code: str) -> Link | None: ...


class MemoryStore:
    """Explicitly nonpersistent, bounded local store; lifetime equals the process."""

    def __init__(self, capacity: int = 1000) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 10_000:
            raise ValueError("capacity must be an integer from 1 to 10000")
        self._capacity = capacity
        self._links: dict[str, Link] = {}
        self._lock = Lock()

    def insert(self, link: Link) -> bool:
        with self._lock:
            if link.code in self._links:
                return False
            if len(self._links) >= self._capacity:
                raise StoreUnavailable
            self._links[link.code] = link
            return True

    def get(self, code: str) -> Link | None:
        with self._lock:
            return self._links.get(code)


def epoch_seconds() -> int:
    return int(time.time())


def random_code() -> str:
    return secrets.token_urlsafe(9)  # Nine random bytes, 72 bits, exactly 12 URL-safe characters.


class Shortener:
    def __init__(
        self,
        store: Store,
        *,
        clock: Callable[[], int] = epoch_seconds,
        codes: Callable[[], str] = random_code,
    ) -> None:
        self.store = store
        self.clock = clock
        self.codes = codes

    def create(self, url: object, ttl_seconds: object = DEFAULT_TTL) -> Link:
        normalized = target_url(url)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL:
            raise ValueError("ttl_seconds must be an integer from 1 to 604800")
        now = self.clock()
        for _ in range(MAX_COLLISIONS):
            code = self.codes()
            if not CODE.fullmatch(code):
                raise StoreUnavailable
            link = Link(code, normalized, now, now + ttl_seconds)
            if self.store.insert(link):
                return link
        raise StoreUnavailable

    def resolve(self, code: str) -> Link:
        if not CODE.fullmatch(code):
            raise NotFound
        link = self.store.get(code)
        if link is None or self.clock() >= link.expires_at:
            raise NotFound
        return link
