"""Real DynamoDB low-level API adapter; callers inject an SDK client."""

from __future__ import annotations

import re
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

from .domain import CODE, MAX_TTL, InvalidTarget, Link, StoreUnavailable, target_url

TABLE = re.compile(r"[A-Za-z0-9_.-]{3,255}\Z", re.ASCII)


class DynamoClient(Protocol):
    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...


class DynamoStore:
    def __init__(self, client: DynamoClient, table: str) -> None:
        if not TABLE.fullmatch(table):
            raise ValueError("invalid table name")
        self.client = client
        self.table = table

    def insert(self, link: Link) -> bool:
        try:
            self.client.put_item(
                TableName=self.table,
                Item={
                    "code": {"S": link.code},
                    "url": {"S": link.url},
                    "created_at": {"N": str(link.created_at)},
                    "expires_at": {"N": str(link.expires_at)},
                },
                ConditionExpression="attribute_not_exists(#code)",
                ExpressionAttributeNames={"#code": "code"},
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise StoreUnavailable from None
        except BotoCoreError:
            raise StoreUnavailable from None

    def get(self, code: str) -> Link | None:
        try:
            response = self.client.get_item(
                TableName=self.table, Key={"code": {"S": code}}, ConsistentRead=True
            )
            if "Item" not in response:
                return None
            item = response["Item"]
            if not isinstance(item, dict) or set(item) != {
                "code",
                "url",
                "created_at",
                "expires_at",
            }:
                raise ValueError
            stored_code, raw_url = item["code"]["S"], item["url"]["S"]
            created, expires = item["created_at"]["N"], item["expires_at"]["N"]
            if (
                not isinstance(stored_code, str)
                or not CODE.fullmatch(stored_code)
                or stored_code != code
                or not isinstance(created, str)
                or not isinstance(expires, str)
                or not re.fullmatch(r"[0-9]{1,12}", created)
                or not re.fullmatch(r"[0-9]{1,12}", expires)
            ):
                raise ValueError
            start, end = int(created), int(expires)
            normalized = target_url(raw_url)
            if normalized != raw_url or not 1 <= end - start <= MAX_TTL:
                raise ValueError
            return Link(stored_code, normalized, start, end)
        except (BotoCoreError, ClientError, KeyError, TypeError, ValueError, InvalidTarget):
            # Corrupt records and SDK failures never become Location headers or error details.
            raise StoreUnavailable from None
