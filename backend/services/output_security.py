"""
Output Security & Audit Logging Service for VAULT.

Implements Step 17 of the VAULT pipeline:
1. Citation allowlist verification: verifies that every citation in the generated output corresponds to an authorized evidence item.
2. Restricted disclosure prevention: scans the generated answer for leaks of sensitive fields (e.g. subject IDs, passwords, unredacted PII).
3. Structured tamper-evident audit logging: logs each inference transaction with user identity, Teacher prompt analysis, policy enforcement, model ID, citations, and hash digest.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("vault.output_security")


class AuditLogEntry(BaseModel):
    """Immutable audit record for an inference transaction."""
    audit_id: str
    timestamp: str
    user_name: str
    user_role: str
    prompt: str
    prompt_threat_detected: bool
    prompt_action: str
    model_id: str
    adapter_id: Optional[str] = None
    cited_sources: List[str] = Field(default_factory=list)
    citations_valid: bool = True
    disclosures_blocked: List[str] = Field(default_factory=list)
    final_status: str  # "served", "rejected_threat", "redacted_output"
    audit_hash: str  # SHA-256 of entry for tamper detection


# Global in-memory audit ledger (survives within session, easily exportable)
_audit_log_ledger: List[AuditLogEntry] = []

# Sensitive patterns that should NEVER appear unredacted in model outputs
RESTRICTED_DISCLOSURE_PATTERNS = [
    (r"P\d{3,5}", "Subject ID"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
    (r"(?:api[_-]?key|secret|password)\s*[:=]\s*\S+", "Credential"),
    (r"confidential\s+patient\s+record", "Confidential Marker"),
]


class OutputSecurityService:
    @staticmethod
    def verify_citations(
        output_text: str,
        authorized_source_ids: List[str],
    ) -> tuple[bool, List[str], List[str]]:
        """
        Extracts all [SOURCE:id] citations from text and validates them
        against the authorized source allowlist.
        Returns: (all_valid, valid_citations, hallucinated_citations)
        """
        cited_in_text = re.findall(r"\[SOURCE:([^\]]+)\]", output_text)
        valid = []
        hallucinated = []
        for c in cited_in_text:
            if c in authorized_source_ids:
                if c not in valid:
                    valid.append(c)
            else:
                if c not in hallucinated:
                    hallucinated.append(c)
        all_valid = len(hallucinated) == 0
        return all_valid, valid, hallucinated

    @staticmethod
    def sanitize_output(
        output_text: str,
        user_role: str = "researcher",
    ) -> tuple[str, List[str]]:
        """
        Scans model output for restricted disclosures (e.g. subject IDs, leaked secrets)
        and redacts them if the user is not an admin.
        Returns: (sanitized_text, list_of_redacted_disclosures)
        """
        if user_role == "admin":
            return output_text, []

        sanitized = output_text
        blocked = []

        for pattern, label in RESTRICTED_DISCLOSURE_PATTERNS:
            matches = re.findall(pattern, sanitized, re.IGNORECASE)
            if matches:
                sanitized = re.sub(pattern, f"[REDACTED_{label.upper().replace(' ', '_')}]", sanitized, flags=re.IGNORECASE)
                blocked.append(label)

        return sanitized, blocked

    @staticmethod
    def record_audit_entry(
        user_name: str,
        user_role: str,
        prompt: str,
        prompt_threat_detected: bool,
        prompt_action: str,
        model_id: str,
        adapter_id: Optional[str],
        cited_sources: List[str],
        citations_valid: bool,
        disclosures_blocked: List[str],
        final_status: str,
    ) -> AuditLogEntry:
        """Creates and appends an immutable audit log entry with SHA-256 fingerprint."""
        now_ts = datetime.now(timezone.utc).isoformat()
        audit_id = f"AUD-{hashlib.sha256(f'{now_ts}:{prompt}:{user_name}'.encode()).hexdigest()[:12].upper()}"

        raw_payload = {
            "audit_id": audit_id,
            "timestamp": now_ts,
            "user_name": user_name,
            "user_role": user_role,
            "prompt": prompt,
            "prompt_threat_detected": prompt_threat_detected,
            "prompt_action": prompt_action,
            "model_id": model_id,
            "adapter_id": adapter_id,
            "cited_sources": cited_sources,
            "citations_valid": citations_valid,
            "disclosures_blocked": disclosures_blocked,
            "final_status": final_status,
        }

        audit_hash = hashlib.sha256(json.dumps(raw_payload, sort_keys=True).encode()).hexdigest()

        entry = AuditLogEntry(
            audit_id=audit_id,
            timestamp=now_ts,
            user_name=user_name,
            user_role=user_role,
            prompt=prompt,
            prompt_threat_detected=prompt_threat_detected,
            prompt_action=prompt_action,
            model_id=model_id,
            adapter_id=adapter_id,
            cited_sources=cited_sources,
            citations_valid=citations_valid,
            disclosures_blocked=disclosures_blocked,
            final_status=final_status,
            audit_hash=audit_hash,
        )

        _audit_log_ledger.append(entry)
        logger.info(f"Audit log recorded: {entry.audit_id} - status={entry.final_status} - hash={entry.audit_hash[:10]}...")
        return entry

    @staticmethod
    def get_audit_logs(limit: int = 50) -> List[AuditLogEntry]:
        """Returns recent audit logs in reverse chronological order."""
        return list(reversed(_audit_log_ledger[-limit:]))
