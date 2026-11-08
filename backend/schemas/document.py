"""
Pydantic schemas for Document operations and responses.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentRead(BaseModel):
    id: int
    filename: str
    stored_filename: str
    file_size: int
    content_type: str
    checksum_sha256: str
    status: str
    doc_metadata: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(BaseModel):
    success: bool
    document: DocumentRead
    message: str


class DocumentListResponse(BaseModel):
    total: int = Field(..., description="Total count of documents")
    items: List[DocumentRead] = Field(..., description="List of document records")
