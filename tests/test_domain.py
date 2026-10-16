from __future__ import annotations

import ipaddress
from concurrent.futures import ThreadPoolExecutor

import pytest

from shortener.domain import (
    CODE,
    MAX_COLLISIONS,
    InvalidTarget,
    Link,
    MemoryStore,
    NotFound,
    Shortener,
    StoreUnavailable,
    random_code,
    target_url,
)

URL = "https://example.com/docs?ref=demo"
CODE_A = "AbCd0123_-xy"
CODE_B = "BcDe1234_-yz"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (URL, URL),
        ("HTTPS://EXAMPLE.COM/docs", "https://example.com/docs"),
        ("http://192.0.2.1:8080/", "http://192.0.2.1:8080/"),
        ("https://[2001:db8::1]/a", "https://[2001:db8::1]/a"),
        ("https://[::ffff:192.0.2.1]/", "https://[::ffff:c000:201]/"),
        ("https://xn--bcher-kva.example/", "https://xn--bcher-kva.example/"),
        ("https://example.com/café?q=雪#é", "https://example.com/caf%C3%A9?q=%E9%9B%AA#%C3%A9"),
        (
            "https://example.com/a%2Fb?x=a+b&x=%2B&next=%252F",
            "https://example.com/a%2Fb?x=a+b&x=%2B&next=%252F",
        ),
        ("https://example.com/?", "https://example.com/?"),
        ("https://example.com/?#", "https://example.com/?#"),
        ("https://example.com/a%20b?q=a%20b", "https://example.com/a%20b?q=a%20b"),
        ("https://example.com:65535/", "https://example.com:65535/"),
        ("https://example.com/a%250D", "https://example.com/a%250D"),
    ],
)
def test_url_policy_preserves_legitimate_query_and_encoding(value, expected):
    assert target_url(value) == expected
    assert target_url(expected) == expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("[::ffff:192.0.2.1]", "[::ffff:c000:201]"),
        ("[::ffff:c000:0201]", "[::ffff:c000:201]"),
        ("[0000:0000:0000:0000:0000:FFFF:C000:0201]", "[::ffff:c000:201]"),
        ("[::FFFF:192.0.2.1]:08443", "[::ffff:c000:201]:8443"),
        ("[::ffff:C000:0201]:65535", "[::ffff:c000:201]:65535"),
        ("[::ffff:0.0.0.0]", "[::ffff:0:0]"),
        ("[::ffff:0.0.0.1]", "[::ffff:0:1]"),
        ("[::ffff:192.0.0.0]", "[::ffff:c000:0]"),
        ("[::ffff:255.255.255.255]", "[::ffff:ffff:ffff]"),
        ("[2001:0DB8:0000:0000:0001:0000:0000:0001]:00443", "[2001:db8::1:0:0:1]:443"),
        ("[0:0:0:0:0:0:0:0]", "[::]"),
        ("[::192.0.2.1]", "[::c000:201]"),
    ],
)
def test_ipv6_hex_canonicalization(host, expected):
    tail = "/docs?next=a%2Fb&ref=demo#part"
    canonical = f"https://{expected}{tail}"
    assert target_url(f"https://{host}{tail}") == canonical
    assert target_url(canonical) == canonical


@pytest.mark.parametrize("host", ["::ffff:192.0.2.1", "::ffff:c000:201", "::FFFF:C000:0201"])
def test_mapped_ipv6_canonicalization_with_dotted_runtime_string(monkeypatch, host):
    original_str = ipaddress.IPv6Address.__str__

    def dotted_mapped_str(address):
        mapped = address.ipv4_mapped
        return f"::ffff:{mapped}" if mapped is not None else original_str(address)

    # Reproduce the newer Python mapped-address representation on older interpreters.
    monkeypatch.setattr(ipaddress.IPv6Address, "__str__", dotted_mapped_str)
    assert ipaddress.IPv6Address(host).compressed == "::ffff:192.0.2.1"
    assert target_url(f"https://[{host}]:8443/") == "https://[::ffff:c000:201]:8443/"


@pytest.mark.parametrize(
    "authority",
    [
        "[::ffff:192.0.2.1",
        "::ffff:192.0.2.1]",
        "[[::ffff:192.0.2.1]]",
        "[::ffff:192.0.2.1]junk",
        "[::ffff:192.0.2.256]",
        "[::ffff:192.0.2.1]:",
        "[::ffff:c000:201]:65536",
        "[::ffff:c000:201]:443:80",
    ],
)
def test_invalid_ipv6_authority(authority):
    with pytest.raises(InvalidTarget):
        target_url(f"https://{authority}/")


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        True,
        [],
        {},
        "",
        "//example.com",
        "javascript:alert(1)",
        "file:///tmp/a",
        "data:text/html,a",
        "ftp://example.com/a",
        "https:///a",
        "https://",
        "https://user:pass@example.com/",
        "https://user@example.com/",
        "https://example.com\r\nLocation:evil",
        "https://example.com/%0d%0ALocation:evil",
        "https://example.com/%00",
        "https://example.com/\x1b[31m",
        " https://example.com",
        "https://example.com/a b",
        "https://example.com\\@evil.example/",
        "https://example.com/%5c",
        "https://example.com/%",
        "https://example.com/%0",
        "https://example.com/%GG",
        "https://example.com/%ff",
        "https://example.com/%C2%85",
        "https://example.com/\u202e",
        "https://example.com/\ud800",
        "https://bücher.example/",
        "https://bad_host.example/",
        "https://.example.com/",
        "https://example.com./",
        "https://-bad.example/",
        "https://bad-.example/",
        "https://localhost/",
        "https://127.1/",
        "https://2130706433/",
        "https://999.999.999.999/",
        "https://example.com:/",
        "https://example.com:0/",
        "https://example.com:65536/",
        "https://example.com:abc/",
        "https://example.com:80:90/",
        "https://[2001:db8::1]evil/",
        "https://[notipv6]/",
        "https://[fe80::1%25zone]/",
        "https://ex%61mple.com/",
        "https://" + "a" * 64 + ".example/",
        "https://xn--.example/",
        "https://example.com/" + "a" * 2048,
        "https://example.com/" + "雪" * 500,
    ],
    ids=lambda value: repr(value)[:60],
)
def test_invalid_target(value):
    with pytest.raises(InvalidTarget):
        target_url(value)


def test_exact_url_bound():
    prefix = "https://example.com/"
    url = prefix + "a" * (2048 - len(prefix))
    assert target_url(url) == url
    with pytest.raises(InvalidTarget):
        target_url(url + "a")


def test_create_resolve_and_exact_expiry_boundary():
    now = [100]
    service = Shortener(MemoryStore(), clock=lambda: now[0], codes=lambda: CODE_A)
    link = service.create(URL, 10)
    assert link == Link(CODE_A, URL, 100, 110)
    now[0] = 109
    assert service.resolve(CODE_A) == link
    now[0] = 110
    with pytest.raises(NotFound):
        service.resolve(CODE_A)
    now[0] = 111
    with pytest.raises(NotFound):
        service.resolve(CODE_A)


@pytest.mark.parametrize("ttl", [0, -1, 604801, True, "10", 1.5, None, []])
def test_bad_ttl(ttl):
    with pytest.raises(ValueError):
        Shortener(MemoryStore()).create(URL, ttl)


@pytest.mark.parametrize("ttl", [1, 604800])
def test_ttl_boundaries(ttl):
    assert Shortener(MemoryStore(), clock=lambda: 100).create(URL, ttl).expires_at == 100 + ttl


def test_collision_retries_do_not_overwrite_even_expired_record():
    store = MemoryStore()
    old = Link(CODE_A, URL, 0, 1)
    assert store.insert(old)
    sequence = iter([CODE_A, CODE_B])
    created = Shortener(store, clock=lambda: 100, codes=lambda: next(sequence)).create(URL)
    assert created.code == CODE_B
    assert store.get(CODE_A) == old


def test_collision_exhaustion_is_bounded():
    calls = []

    def generate():
        calls.append(1)
        return CODE_A

    store = MemoryStore()
    store.insert(Link(CODE_A, URL, 0, 1))
    with pytest.raises(StoreUnavailable):
        Shortener(store, codes=generate).create(URL)
    assert len(calls) == MAX_COLLISIONS


def test_bad_injected_code_never_stored():
    store = MemoryStore()
    with pytest.raises(StoreUnavailable):
        Shortener(store, codes=lambda: "../bad").create(URL)
    assert store.get("../bad") is None


@pytest.mark.parametrize(
    "code", ["", "../bad", "a" * 11, "a" * 13, "%41" * 12, CODE_A + "/", "\x1b" * 12]
)
def test_bad_resolve_codes(code):
    with pytest.raises(NotFound):
        Shortener(MemoryStore()).resolve(code)


def test_random_code_uses_crypto_bytes(monkeypatch):
    calls = []

    def token(count):
        calls.append(count)
        return CODE_A

    monkeypatch.setattr("shortener.domain.secrets.token_urlsafe", token)
    assert random_code() == CODE_A
    assert calls == [9]
    assert CODE.fullmatch(CODE_A)


def test_capacity_is_bounded_and_memory_is_not_shared():
    store = MemoryStore(capacity=1)
    first = Link(CODE_A, URL, 0, 1)
    assert store.insert(first)
    assert store.insert(first) is False
    with pytest.raises(StoreUnavailable):
        store.insert(Link(CODE_B, URL, 0, 1))
    assert MemoryStore().get(CODE_A) is None


def test_memory_insert_is_atomic_for_concurrent_requests():
    store = MemoryStore()
    with ThreadPoolExecutor(max_workers=4) as workers:
        outcomes = list(workers.map(store.insert, [Link(CODE_A, URL, 0, 1)] * 20))
    assert outcomes.count(True) == 1


@pytest.mark.parametrize("capacity", [0, 10001, True, "100"])
def test_invalid_memory_capacity(capacity):
    with pytest.raises(ValueError):
        MemoryStore(capacity)
