from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3

from app.config import get_config

_ddb_resource = None


def get_ddb_resource():
    global _ddb_resource
    if _ddb_resource is None:
        _ddb_resource = boto3.resource("dynamodb")
    return _ddb_resource


def get_table():
    config = get_config()
    return get_ddb_resource().Table(config.backend_table_name)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def decimal_to_python(obj: Any) -> Any:
    """Convert DynamoDB Decimal types to Python native types."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_python(i) for i in obj]
    return obj


def batch_delete_items(items: list[dict]) -> None:
    """Batch delete items from DynamoDB."""
    table = get_table()
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
