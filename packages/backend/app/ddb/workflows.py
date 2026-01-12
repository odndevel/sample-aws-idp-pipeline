from boto3.dynamodb.conditions import Key

from app.ddb.client import decimal_to_python, get_table


def make_workflow_link_key(project_id: str, workflow_id: str) -> dict:
    return {"PK": f"PROJ#{project_id}", "SK": f"WF#{workflow_id}"}


def make_workflow_meta_key(workflow_id: str) -> dict:
    return {"PK": f"WF#{workflow_id}", "SK": "META"}


def get_workflow_meta(workflow_id: str) -> dict | None:
    table = get_table()
    response = table.get_item(Key=make_workflow_meta_key(workflow_id))
    item = response.get("Item")
    return decimal_to_python(item) if item else None


def query_workflows(project_id: str) -> list[dict]:
    """Query all workflows for a project."""
    table = get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"PROJ#{project_id}") & Key("SK").begins_with("WF#"),
    )
    return [decimal_to_python(item) for item in response.get("Items", [])]


def query_workflow_items(workflow_id: str) -> list[dict]:
    """Query all items under WF#{workflow_id} with pagination."""
    table = get_table()
    items = []
    response = table.query(KeyConditionExpression=Key("PK").eq(f"WF#{workflow_id}"))
    items.extend(response.get("Items", []))

    while response.get("LastEvaluatedKey"):
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"WF#{workflow_id}"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    return items


def query_workflow_segments(workflow_id: str) -> list[dict]:
    """Query all segments for a workflow."""
    table = get_table()
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"WF#{workflow_id}") & Key("SK").begins_with("SEG#"),
    )
    return [decimal_to_python(item) for item in response.get("Items", [])]


def delete_workflow_link(project_id: str, workflow_id: str) -> None:
    table = get_table()
    table.delete_item(Key=make_workflow_link_key(project_id, workflow_id))
