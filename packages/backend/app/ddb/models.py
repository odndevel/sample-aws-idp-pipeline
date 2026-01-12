from pydantic import BaseModel


class ProjectData(BaseModel):
    project_id: str
    name: str
    description: str
    status: str


class Project(BaseModel):
    data: ProjectData
    created_at: str
    updated_at: str


class DocumentData(BaseModel):
    document_id: str
    project_id: str
    name: str
    file_type: str
    file_size: int
    status: str
    s3_key: str


class Document(BaseModel):
    data: DocumentData
    created_at: str
    updated_at: str
