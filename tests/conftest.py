"""Every test blocks public networking and uses workspace-only dummy AWS config."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "loopback: permit only numeric IPv4 loopback HTTP")


def pytest_sessionstart(session):
    explicit = session.config.getoption("basetemp")
    if explicit is not None:
        Path(explicit).parent.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def offline(monkeypatch, request):
    root = Path(__file__).resolve().parents[1]
    temporary = root / ".tmp"
    temporary.mkdir(exist_ok=True)
    config = temporary / "test-aws-config"
    config.write_text("[default]\nregion = us-east-1\n", encoding="utf-8")
    for name in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.setenv(name, str(config))
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "offline-placeholder")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_PROFILE", "default")
    monkeypatch.setenv("AWS_DEFAULT_PROFILE", "default")
    original_connect = socket.socket.connect
    original_resolve = socket.getaddrinfo
    loopback = request.node.get_closest_marker("loopback") is not None

    def connect(sock, address):
        if loopback and isinstance(address, tuple) and address[0] == "127.0.0.1":
            return original_connect(sock, address)
        raise AssertionError("non-loopback network access is forbidden")

    def resolve(host, *args, **kwargs):
        if loopback and host == "127.0.0.1":
            return original_resolve(host, *args, **kwargs)
        raise AssertionError("DNS/network access is forbidden")

    def blocked(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
