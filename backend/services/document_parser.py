"""
Multi-Format Document Ingestion & Text Preprocessing Service for VAULT.

Implements Steps 1 & 2 of the VAULT pipeline:
1. Data Ingestion: PDF, CSV, Excel, JSON, plain text documents.
2. Python Preprocessing: Text extraction, chunking, metadata extraction, canonical SHA-256 hashing.
"""

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("vault.parser")


class DocumentChunk(BaseModel):
    chunk_index: int
    text: str
    token_estimate: int
    chunk_hash: str


class ParsedDocument(BaseModel):
    filename: str
    format: str
    size_bytes: int
    content_hash: str
    extracted_text: str
    structured_records: List[Dict[str, Any]] = Field(default_factory=list)
    chunks: List[DocumentChunk] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    ingested_at: str


class DocumentParserService:
    @staticmethod
    def compute_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def chunk_text(text: str, max_chunk_chars: int = 1000, overlap_chars: int = 150) -> List[DocumentChunk]:
        """Splits long document text into overlapping chunks for analysis and indexing."""
        if not text:
            return []

        chunks: List[DocumentChunk] = []
        start = 0
        idx = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + max_chunk_chars, text_len)
            chunk_slice = text[start:end].strip()
            if chunk_slice:
                c_hash = hashlib.sha256(chunk_slice.encode()).hexdigest()
                chunks.append(DocumentChunk(
                    chunk_index=idx,
                    text=chunk_slice,
                    token_estimate=max(1, len(chunk_slice) // 4),
                    chunk_hash=c_hash,
                ))
                idx += 1
            if end >= text_len:
                break
            start += max_chunk_chars - overlap_chars

        return chunks

    @classmethod
    def parse_document(
        cls,
        filename: str,
        content_bytes: bytes,
    ) -> ParsedDocument:
        """
        Parses uploaded file bytes according to file extension.
        Supports: .json, .csv, .txt, .tsv, .xlsx (metadata/text fallback), and .pdf.
        """
        content_hash = cls.compute_sha256(content_bytes)
        size_bytes = len(content_bytes)
        ext = Path(filename).suffix.lower()
        now_ts = datetime.now(timezone.utc).isoformat()

        extracted_text = ""
        structured_records: List[Dict[str, Any]] = []
        meta: Dict[str, Any] = {
            "original_filename": filename,
            "extension": ext,
            "size_bytes": size_bytes,
        }

        if ext == ".json":
            try:
                raw_str = content_bytes.decode("utf-8")
                extracted_text = raw_str
                parsed_json = json.loads(raw_str)
                if isinstance(parsed_json, list):
                    structured_records = [item for item in parsed_json if isinstance(item, dict)]
                elif isinstance(parsed_json, dict):
                    structured_records = [parsed_json]
                meta["json_keys"] = list(structured_records[0].keys()) if structured_records else []
            except Exception as e:
                logger.warning(f"Failed to parse JSON '{filename}': {e}")
                extracted_text = content_bytes.decode("utf-8", errors="replace")

        elif ext in (".csv", ".tsv"):
            delimiter = "\t" if ext == ".tsv" else ","
            try:
                text_stream = io.StringIO(content_bytes.decode("utf-8", errors="replace"))
                reader = csv.DictReader(text_stream, delimiter=delimiter)
                lines = []
                for row in reader:
                    structured_records.append(dict(row))
                    lines.append(" | ".join(f"{k}: {v}" for k, v in row.items()))
                extracted_text = "\n".join(lines)
                meta["row_count"] = len(structured_records)
                meta["column_count"] = len(reader.fieldnames) if reader.fieldnames else 0
            except Exception as e:
                logger.warning(f"Failed to parse CSV/TSV '{filename}': {e}")
                extracted_text = content_bytes.decode("utf-8", errors="replace")

        elif ext in (".txt", ".md", ".log"):
            extracted_text = content_bytes.decode("utf-8", errors="replace")
            meta["line_count"] = len(extracted_text.splitlines())

        elif ext == ".pdf":
            # Lightweight PDF text extraction if pypdf/fitz available; otherwise extract readable ASCII streams
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                pages_text = [page.extract_text() or "" for page in reader.pages]
                extracted_text = "\n\n".join(pages_text)
                meta["page_count"] = len(reader.pages)
            except Exception:
                # Robust binary text fallback
                extracted_text = content_bytes.decode("latin-1", errors="ignore")
                meta["note"] = "Extracted via binary fallback"

        else:
            # Generic binary or unknown file
            extracted_text = content_bytes.decode("utf-8", errors="replace")
            meta["note"] = "Generic text decode"

        chunks = cls.chunk_text(extracted_text)

        return ParsedDocument(
            filename=filename,
            format=ext.lstrip("."),
            size_bytes=size_bytes,
            content_hash=content_hash,
            extracted_text=extracted_text,
            structured_records=structured_records,
            chunks=chunks,
            metadata=meta,
            ingested_at=now_ts,
        )
