import contextlib

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_config
from app.ddb import (
    Project,
    batch_delete_items,
    get_project_item,
    now_iso,
    put_project_item,
    query_all_project_items,
    query_projects,
    update_project_data,
)
from app.ddb.workflows import query_workflows

router = APIRouter(prefix="/projects", tags=["projects"])


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
    created_at: str
    updated_at: str | None = None

    @staticmethod
    def from_project(project: Project) -> "ProjectResponse":
        return ProjectResponse(
            project_id=project.data.project_id,
            name=project.data.name,
            description=project.data.description,
            status=project.data.status,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )


@router.get("")
def list_projects() -> list[ProjectResponse]:
    projects = query_projects()
    return [ProjectResponse.from_project(p) for p in projects]


@router.get("/{project_id}")
def get_project(project_id: str) -> ProjectResponse:
    project = get_project_item(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse.from_project(project)


@router.post("")
def create_project(request: ProjectCreate) -> ProjectResponse:
    existing = get_project_item(request.project_id)
    if existing:
        raise HTTPException(status_code=409, detail="Project already exists")

    now = now_iso()
    data = {
        "project_id": request.project_id,
        "name": request.name,
        "description": request.description or "",
        "status": "active",
    }

    put_project_item(request.project_id, data)

    return ProjectResponse(
        project_id=request.project_id,
        name=request.name,
        description=request.description or "",
        status="active",
        created_at=now,
        updated_at=now,
    )


@router.put("/{project_id}")
def update_project(project_id: str, request: ProjectUpdate) -> ProjectResponse:
    existing = get_project_item(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    data = existing.data.model_dump()

    if request.name is not None:
        data["name"] = request.name

    if request.description is not None:
        data["description"] = request.description

    update_project_data(project_id, data)

    return get_project(project_id)


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict:
    """Delete a project and all related data (documents, workflows, S3, LanceDB)."""
    config = get_config()
    s3 = _get_s3_client()

    existing = get_project_item(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    deleted_info = {"project_id": project_id}

    # 1. Get all items under this project
    project_items = query_all_project_items(project_id)

    # Extract document IDs and collect workflow IDs
    document_ids = [item["SK"].replace("DOC#", "") for item in project_items if item["SK"].startswith("DOC#")]
    workflow_ids = []
    workflow_items = []
    for doc_id in document_ids:
        wf_items = query_workflows(doc_id)
        for wf_item in wf_items:
            workflow_ids.append(wf_item["SK"].replace("WF#", ""))
            workflow_items.append(wf_item)

    deleted_info["workflow_count"] = len(workflow_ids)

    # 2. Delete from LanceDB (all workflows)
    if workflow_ids:
        try:
            import lancedb

            bucket_name = _get_ssm_parameter("/idp-v2/lancedb/storage/bucket-name")
            lock_table_name = _get_ssm_parameter("/idp-v2/lancedb/lock/table-name")
            db = lancedb.connect(f"s3+ddb://{bucket_name}/idp-v2?ddbTableName={lock_table_name}")
            if "documents" in db.table_names():
                lance_table = db.open_table("documents")
                for workflow_id in workflow_ids:
                    with contextlib.suppress(Exception):
                        lance_table.delete(f"workflow_id = '{workflow_id}'")
                deleted_info["lancedb_deleted"] = True
        except Exception as e:
            deleted_info["lancedb_error"] = str(e)

    # 3. Delete workflow items from DynamoDB
    if workflow_items:
        batch_delete_items(workflow_items)
        deleted_info["workflow_items_deleted"] = len(workflow_items)

    # 4. Delete from S3 - entire project folder
    project_prefix = f"projects/{project_id}/"
    with contextlib.suppress(Exception):
        s3_deleted = _delete_s3_prefix(s3, config.document_storage_bucket_name, project_prefix)
        deleted_info["s3_objects_deleted"] = s3_deleted

    # 5. Delete all project items from DynamoDB (PROJ#, DOC#*, WF#* links)
    batch_delete_items(project_items)

    deleted_info["project_items_deleted"] = len(project_items)

    return {"message": f"Project {project_id} deleted", "details": deleted_info}


_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _get_ssm_parameter(key: str) -> str:
    """Get SSM parameter value."""
    ssm = boto3.client("ssm")
    response = ssm.get_parameter(Name=key)
    return response["Parameter"]["Value"]


def _delete_s3_prefix(s3_client, bucket: str, prefix: str) -> int:
    """Delete all objects under a prefix."""
    deleted_count = 0
    paginator = s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue

        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
        deleted_count += len(delete_keys)

    return deleted_count
