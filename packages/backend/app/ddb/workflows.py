from boto3.dynamodb.conditions import Key

from app.ddb.client import get_table
from app.ddb.models import Segment, Workflow


def make_workflow_key(document_id: str, workflow_id: str) -> dict:
    return {"PK": f"DOC#{document_id}", "SK": f"WF#{workflow_id}"}


def get_workflow_item(document_id: str, workflow_id: str) -> Workflow | None:
    table = get_table()
    response = table.get_item(Key=make_workflow_key(document_id, workflow_id))
    item = response.get("Item")
    return Workflow(**item) if item else None


def query_workflows(document_id: str) -> list[Workflow]:
    """Query all workflows for a document."""
    table = get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"DOC#{document_id}") & Key("SK").begins_with("WF#"),
    )
    return [Workflow(**item) for item in response.get("Items", [])]


def query_workflow_segments(workflow_id: str) -> list[Segment]:
    """Query all segments for a workflow."""
    table = get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"WF#{workflow_id}") & Key("SK").begins_with("SEG#"),
    )
    return [Segment(**item) for item in response.get("Items", [])]


def delete_workflow_item(document_id: str, workflow_id: str) -> None:
    table = get_table()
    table.delete_item(Key=make_workflow_key(document_id, workflow_id))
