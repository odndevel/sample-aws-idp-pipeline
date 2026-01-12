from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ddb.workflows import get_workflow_item, query_workflow_segments, query_workflows

router = APIRouter(prefix="/documents/{document_id}/workflows", tags=["workflows"])


class WorkflowListResponse(BaseModel):
    workflow_id: str
    status: str
    file_name: str
    file_uri: str
    created_at: str
    updated_at: str


class SegmentData(BaseModel):
    segment_index: int
    image_uri: str
    image_url: str | None = None
    bda_indexer: str
    format_parser: str
    image_analysis: list[dict]


class WorkflowDetailResponse(BaseModel):
    workflow_id: str
    document_id: str
    status: str
    file_name: str
    file_uri: str
    file_type: str
    total_segments: int
    created_at: str
    updated_at: str
    segments: list[SegmentData]


@router.get("")
def list_workflows(document_id: str) -> list[WorkflowListResponse]:
    """List all workflows for a document."""
    workflows = query_workflows(document_id)

    return [
        WorkflowListResponse(
            workflow_id=wf.SK.replace("WF#", "") if wf.SK.startswith("WF#") else wf.SK,
            status=wf.data.status,
            file_name=wf.data.file_name,
            file_uri=wf.data.file_uri,
            created_at=wf.created_at,
            updated_at=wf.updated_at,
        )
        for wf in workflows
    ]


@router.get("/{workflow_id}")
def get_workflow(document_id: str, workflow_id: str) -> WorkflowDetailResponse:
    """Get a single workflow with segments."""
    wf = get_workflow_item(document_id, workflow_id)

    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Get segments
    segment_items = query_workflow_segments(workflow_id)
    segments = [
        SegmentData(
            segment_index=seg.data.segment_index,
            image_uri=seg.data.image_uri,
            image_url=None,
            bda_indexer=seg.data.bda_indexer,
            format_parser=seg.data.format_parser,
            image_analysis=[ia.model_dump() for ia in seg.data.image_analysis],
        )
        for seg in segment_items
    ]

    # Sort segments by index
    segments.sort(key=lambda s: s.segment_index)

    return WorkflowDetailResponse(
        workflow_id=workflow_id,
        document_id=document_id,
        status=wf.data.status,
        file_name=wf.data.file_name,
        file_uri=wf.data.file_uri,
        file_type=wf.data.file_type,
        total_segments=wf.data.total_segments or len(segments),
        created_at=wf.created_at,
        updated_at=wf.updated_at,
        segments=segments,
    )
