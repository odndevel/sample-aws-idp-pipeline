from datetime import UTC, datetime

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_config

router = APIRouter(prefix="/projects", tags=["projects"])

_ddb_resource = None


def get_ddb_resource():
    global _ddb_resource
    if _ddb_resource is None:
        _ddb_resource = boto3.resource("dynamodb")
    return _ddb_resource


def get_table():
    config = get_config()
    return get_ddb_resource().Table(config.backend_table_name)


class ProjectCreate(BaseModel):
    project_id: str
    name: str
    description: str | None = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str
    status: str
    started_at: str
    ended_at: str | None = None


@router.get("")
def list_projects() -> list[ProjectResponse]:
    table = get_table()
    response = table.scan(
        FilterExpression="begins_with(PK, :pk) AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": "PROJ#", ":sk": "PROJ#"},
    )

    projects = []
    for item in response.get("Items", []):
        data = item.get("data", {})
        projects.append(
            ProjectResponse(
                project_id=data.get("project_id", ""),
                name=data.get("name", ""),
                description=data.get("description", ""),
                status=data.get("status", "active"),
                started_at=item.get("started_at", ""),
                ended_at=item.get("ended_at"),
            )
        )

    return projects


@router.get("/{project_id}")
def get_project(project_id: str) -> ProjectResponse:
    table = get_table()
    response = table.get_item(Key={"PK": f"PROJ#{project_id}", "SK": f"PROJ#{project_id}"})

    item = response.get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Project not found")

    data = item.get("data", {})
    return ProjectResponse(
        project_id=data.get("project_id", ""),
        name=data.get("name", ""),
        description=data.get("description", ""),
        status=data.get("status", "active"),
        started_at=item.get("started_at", ""),
        ended_at=item.get("ended_at"),
    )


@router.post("")
def create_project(request: ProjectCreate) -> ProjectResponse:
    table = get_table()
    now = datetime.now(UTC).isoformat()

    existing = table.get_item(Key={"PK": f"PROJ#{request.project_id}", "SK": f"PROJ#{request.project_id}"})
    if existing.get("Item"):
        raise HTTPException(status_code=409, detail="Project already exists")

    item = {
        "PK": f"PROJ#{request.project_id}",
        "SK": f"PROJ#{request.project_id}",
        "data": {
            "project_id": request.project_id,
            "name": request.name,
            "description": request.description or "",
            "status": "active",
        },
        "started_at": now,
        "ended_at": now,
    }

    table.put_item(Item=item)

    return ProjectResponse(
        project_id=request.project_id,
        name=request.name,
        description=request.description or "",
        status="active",
        started_at=now,
        ended_at=now,
    )


@router.put("/{project_id}")
def update_project(project_id: str, request: ProjectUpdate) -> ProjectResponse:
    table = get_table()

    existing = table.get_item(Key={"PK": f"PROJ#{project_id}", "SK": f"PROJ#{project_id}"})
    if not existing.get("Item"):
        raise HTTPException(status_code=404, detail="Project not found")

    now = datetime.now(UTC).isoformat()
    item = existing.get("Item")
    data = item.get("data", {})

    if request.name is not None:
        data["name"] = request.name

    if request.description is not None:
        data["description"] = request.description

    table.update_item(
        Key={"PK": f"PROJ#{project_id}", "SK": f"PROJ#{project_id}"},
        UpdateExpression="SET #data = :data, ended_at = :ended_at",
        ExpressionAttributeNames={"#data": "data"},
        ExpressionAttributeValues={":data": data, ":ended_at": now},
    )

    return get_project(project_id)


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict:
    table = get_table()

    existing = table.get_item(Key={"PK": f"PROJ#{project_id}", "SK": f"PROJ#{project_id}"})
    if not existing.get("Item"):
        raise HTTPException(status_code=404, detail="Project not found")

    table.delete_item(Key={"PK": f"PROJ#{project_id}", "SK": f"PROJ#{project_id}"})

    return {"message": f"Project {project_id} deleted"}
