from __future__ import annotations

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from shortener import aws
from shortener.domain import Link, Shortener, StoreUnavailable
from shortener.dynamodb import DynamoStore

TABLE = "offline-links"
CODE = "AbCd0123_-xy"
URL = "https://example.com/docs?ref=demo"
LINK = Link(CODE, URL, 100, 200)
ITEM = {
    "code": {"S": CODE},
    "url": {"S": URL},
    "created_at": {"N": "100"},
    "expires_at": {"N": "200"},
}
PUT = {
    "TableName": TABLE,
    "Item": ITEM,
    "ConditionExpression": "attribute_not_exists(#code)",
    "ExpressionAttributeNames": {"#code": "code"},
}
GET = {"TableName": TABLE, "Key": {"code": {"S": CODE}}, "ConsistentRead": True}


@pytest.fixture
def client():
    # Explicit dummy values and workspace config from conftest; never discover credentials.
    session = boto3.Session(
        aws_access_key_id="offline",
        aws_secret_access_key="offline",  # noqa: S106 -- explicit noncredential for offline Stubber
        aws_session_token="offline",  # noqa: S106 -- explicit noncredential for offline Stubber
        region_name="us-east-1",
    )
    return session.client("dynamodb", config=Config(retries={"total_max_attempts": 1}))


def test_actual_sdk_conditional_put_and_consistent_read(client):
    with Stubber(client) as stub:
        stub.add_response("put_item", {}, PUT)
        stub.add_response("get_item", {"Item": ITEM}, GET)
        store = DynamoStore(client, TABLE)
        assert store.insert(LINK) is True
        assert store.get(CODE) == LINK
        stub.assert_no_pending_responses()


def test_collision_is_only_false_condition_and_exhaustion_does_not_retry_other_errors(client):
    with Stubber(client) as stub:
        for _ in range(5):
            stub.add_client_error(
                "put_item", "ConditionalCheckFailedException", "synthetic", expected_params=PUT
            )
        with pytest.raises(StoreUnavailable):
            Shortener(DynamoStore(client, TABLE), clock=lambda: 100, codes=lambda: CODE).create(
                URL, 100
            )
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("operation,params", [("put_item", PUT), ("get_item", GET)])
@pytest.mark.parametrize(
    "code",
    ["AccessDeniedException", "ProvisionedThroughputExceededException", "InternalServerError"],
)
def test_sdk_failures_are_sanitized(client, operation, params, code):
    with Stubber(client) as stub:
        stub.add_client_error(operation, code, "sensitive URL?token=secret", expected_params=params)
        store = DynamoStore(client, TABLE)
        with pytest.raises(StoreUnavailable) as exc:
            store.insert(LINK) if operation == "put_item" else store.get(CODE)
        assert str(exc.value) == ""
        assert exc.value.__suppress_context__
        stub.assert_no_pending_responses()


def test_missing_item_and_expired_item_still_returned_by_sdk(client):
    with Stubber(client) as stub:
        stub.add_response("get_item", {}, GET)
        stub.add_response("get_item", {"Item": ITEM}, GET)
        store = DynamoStore(client, TABLE)
        assert store.get(CODE) is None
        # Storage keeps the expired item; the domain enforces expiry independently of TTL.
        assert store.get(CODE).expires_at == 200
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "item",
    [
        {},
        {**ITEM, "unexpected": {"S": "x"}},
        {**ITEM, "code": {"S": "wrong"}},
        {**ITEM, "url": {"S": "https://example.com/%0d%0aBad:injected"}},
        {**ITEM, "url": {"S": "HTTPS://EXAMPLE.COM"}},
        {**ITEM, "created_at": {"N": "1.5"}},
        {**ITEM, "expires_at": {"N": "100"}},
        {**ITEM, "expires_at": {"N": "999999999999"}},
        {**ITEM, "created_at": {"S": "100"}},
    ],
)
def test_corrupt_items_cannot_become_redirects(client, item):
    with Stubber(client) as stub:
        stub.add_response("get_item", {"Item": item}, GET)
        with pytest.raises(StoreUnavailable):
            DynamoStore(client, TABLE).get(CODE)


def test_network_sdk_error_is_sanitized():
    class FailedClient:
        def put_item(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://synthetic.invalid/secret")

        def get_item(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://synthetic.invalid/secret")

    store = DynamoStore(FailedClient(), TABLE)
    with pytest.raises(StoreUnavailable):
        store.insert(LINK)
    with pytest.raises(StoreUnavailable):
        store.get(CODE)


def test_factory_applies_timeout_retry_and_endpoint_configuration(monkeypatch, client):
    seen = []

    def factory(service, **kwargs):
        seen.append((service, kwargs))
        return client

    monkeypatch.setattr(boto3, "client", factory)
    monkeypatch.setenv("TABLE_NAME", TABLE)
    application = aws.make_application()
    assert application.service.store.table == TABLE
    service, kwargs = seen[0]
    assert service == "dynamodb"
    config = kwargs["config"]
    assert config.connect_timeout == 1
    assert config.read_timeout == 2
    assert config.retries == {"mode": "standard", "total_max_attempts": 2}
    assert config.ignore_configured_endpoint_urls is True


@pytest.mark.parametrize("name", ["", "ab", "../bad", "a" * 256])
def test_table_configuration_rejected(client, name):
    with pytest.raises(ValueError):
        DynamoStore(client, name)
