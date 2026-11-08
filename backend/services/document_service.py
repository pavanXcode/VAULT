"""
Document service managing offline storage, SHA-256 checksums, and metadata indexing.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
from typing import List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy.orm import Session
from backend.config import get_settings
from backend.models.document import Document
from backend.schemas.document import DocumentRead

settings = get_settings()


class DocumentService:
    @staticmethod
    async def save_upload(
        upload_file: UploadFile,
        db: Session,
    ) -> Tuple[Document, bool]:
        """
        Saves an uploaded file to the local storage directory chunk by chunk,
        calculates SHA-256 hash, and records the document entry in the database.
        Returns (document, is_new).
        """
        upload_dir = settings.resolved_upload_path
        original_filename = Path(upload_file.filename or "unnamed_file").name
        ext = Path(original_filename).suffix

        # Generate a collision-resistant unique filename
        stored_filename = f"{uuid.uuid4().hex[:12]}_{original_filename}"
        destination_path = upload_dir / stored_filename

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(destination_path, "wb") as buffer:
                while chunk := await upload_file.read(1024 * 64):  # 64 KB chunks
                    total_bytes += len(chunk)
                    if total_bytes > settings.max_upload_size_bytes:
                        raise ValueError(
                            f"File size exceeds maximum limit of {settings.max_upload_size_bytes} bytes."
                        )
                    hasher.update(chunk)
                    buffer.write(chunk)
        except Exception:
            # Clean up partially written file if write failed
            if destination_path.exists():
                destination_path.unlink()
            raise

        checksum = hasher.hexdigest()

        # Check if an identical document by SHA-256 already exists in DB
        existing = db.query(Document).filter(Document.checksum_sha256 == checksum).first()
        if existing:
            # Duplicate file detected: clean up the redundant newly saved file
            if destination_path.exists():
                destination_path.unlink()
            return existing, False

        doc_metadata = json.dumps(
            {
                "original_name": original_filename,
                "file_extension": ext,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        doc = Document(
            filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(destination_path.resolve()),
            file_size=total_bytes,
            content_type=upload_file.content_type or "application/octet-stream",
            checksum_sha256=checksum,
            status="uploaded",
            doc_metadata=doc_metadata,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc, True

    @staticmethod
    def list_documents(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
    ) -> Tuple[List[Document], int]:
        """Returns paginated documents and total count."""
        query = db.query(Document)
        if status:
            query = query.filter(Document.status == status)
        total = query.count()
        docs = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
        return docs, total

    @staticmethod
    def get_by_id(db: Session, doc_id: int) -> Optional[Document]:
        """Retrieves a single document by its integer ID."""
        return db.query(Document).filter(Document.id == doc_id).first()
