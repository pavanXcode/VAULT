"""
Document ORM model for offline file management and provenance tracking.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from backend.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(100), default="application/octet-stream")
    checksum_sha256 = Column(String(64), nullable=False, index=True)
    status = Column(String(50), default="uploaded", nullable=False)
    doc_metadata = Column(Text, nullable=True)  # JSON-encoded metadata string
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "stored_filename": self.stored_filename,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "checksum_sha256": self.checksum_sha256,
            "status": self.status,
            "doc_metadata": self.doc_metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
