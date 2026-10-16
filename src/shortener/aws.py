"""Undeployed Lambda REST proxy v1 entry point; no AWS activity on import."""

from __future__ import annotations

import os
from typing import Any

from .domain import Shortener
from .http import Application, Rejected, error, gateway_request

_application: Application | None = None


def make_application() -> Application:
    # These imports and client construction occur only on an actual valid invocation.
    import boto3
    from botocore.config import Config

    from .dynamodb import DynamoStore

    table = os.environ["TABLE_NAME"]
    config = Config(
        connect_timeout=1,
        read_timeout=2,
        retries={"mode": "standard", "total_max_attempts": 2},
        max_pool_connections=2,
        ignore_configured_endpoint_urls=True,
    )
    return Application(
        Shortener(DynamoStore(boto3.client("dynamodb", config=config), table)), print
    )


def lambda_handler(event: object, context: object) -> dict[str, Any]:
    del context
    global _application
    try:
        request = gateway_request(event)
    except Rejected as exc:
        print('{"event":"http_result","route":"unknown","status":' + str(exc.response.status) + "}")
        return exc.response.gateway()
    try:
        if _application is None:
            _application = make_application()
        return _application.handle(*request).gateway()
    except Exception:
        # No raw SDK error, event, request context, body, URL or key in runtime logs.
        print('{"event":"http_result","route":"unknown","status":503}')
        return error(503, "unavailable", **{"Retry-After": "1"}).gateway()
