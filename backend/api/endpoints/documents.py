"""
Document upload and retrieval endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.document import DocumentListResponse, DocumentRead, DocumentUploadResponse
from backend.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("", response_model=DocumentListResponse, summary="List stored documents")
def list_documents(
    skip: int = Query(default=0, ge=0, description="Offset"),
    limit: int = Query(default=100, ge=1, le=500, description="Page size"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
):
    """
    Returns paginated metadata for all uploaded datasets and documents.
    """
    docs, total = DocumentService.list_documents(db, skip=skip, limit=limit, status=status_filter)
    return DocumentListResponse(
        total=total,
        items=[DocumentRead.model_validate(d) for d in docs],
    )


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a dataset or document",
)
async def upload_document(
    file: UploadFile = File(..., description="Document or dataset file to store offline"),
    db: Session = Depends(get_db),
):
    """
    Accepts multipart file uploads, persists the file offline in the data directory,
    computes its SHA-256 checksum for provenance tracking, and records it in the database.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a non-empty filename.",
        )

    try:
        doc, is_new = await DocumentService.save_upload(file, db)
        message = "File uploaded and indexed successfully." if is_new else "Identical file already indexed (deduplicated)."
        return DocumentUploadResponse(
            success=True,
            document=DocumentRead.model_validate(doc),
            message=message,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document upload: {str(exc)}",
        )
