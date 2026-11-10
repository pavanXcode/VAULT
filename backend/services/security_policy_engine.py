"""
Security Policy Engine — Deterministic Python enforcement layer for VAULT.

DESIGN PRINCIPLE: The Teacher LLM (Qwen) RECOMMENDS decisions.
This engine VALIDATES those recommendations against deterministic rules
and ENFORCES the final policy decision. It NEVER blindly trusts Qwen.

Enforcement capabilities:
- Validate Teacher output against RBAC and organizational policies
- Apply redaction based on sensitivity classifications
- Quarantine suspicious data
- Check explicit training-use authorization
- Produce auditable enforcement records
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.services.auth_service import UserSession
from backend.services.teacher_llm_service import (
    TeacherDecision,
    VALID_ACTIONS,
    VALID_SENSITIVITY,
)

logger = logging.getLogger("vault.security_policy")

# ──────────────────────────────────────────────────────────────
# Enforcement Result Schema
# ──────────────────────────────────────────────────────────────

class EnforcementResult(BaseModel):
    """The final, authoritative policy decision after validating the Teacher's recommendation."""
    # Final decisions (Python-enforced, not Qwen-recommended)
    final_action: str = Field(..., description="Enforced action: ALLOW / REDACT / RESTRICT / QUARANTINE / REJECT / HUMAN_REVIEW")
    training_authorized: bool = Field(default=False, description="Whether training use is explicitly authorized")
    access_granted: bool = Field(default=False, description="Whether the user has access to this data")

    # Redaction
    redacted_fields: List[str] = Field(default_factory=list, description="Fields that were redacted by policy")
    redacted_content: Optional[str] = Field(default=None, description="Content after applying redactions")

    # Quarantine
    quarantined: bool = Field(default=False, description="Whether data was quarantined for investigation")
    quarantine_reason: Optional[str] = Field(default=None, description="Why quarantined")

    # Audit trail
    teacher_recommendation: str = Field(default="", description="What the Teacher recommended")
    policy_overrides: List[str] = Field(default_factory=list, description="Where Python overrode the Teacher")
    enforcement_timestamp: str = Field(default="", description="ISO 8601")
    enforcement_hash: str = Field(default="", description="SHA-256 of the enforcement record for tamper detection")


# ──────────────────────────────────────────────────────────────
# Role-Based Access Matrix
# ──────────────────────────────────────────────────────────────

# Maps sensitivity levels to minimum role requirements
SENSITIVITY_ROLE_REQUIREMENTS = {
    "PUBLIC": ["researcher", "admin", "external"],
    "INTERNAL": ["researcher", "admin"],
    "CONFIDENTIAL": ["researcher", "admin"],
    "HIGHLY_RESTRICTED": ["admin"],
}

# Fields that must ALWAYS be redacted for non-admin users
MANDATORY_REDACTION_FIELDS = {
    "subject_id", "patient_id", "ssn", "social_security",
    "password", "api_key", "secret_key", "private_key",
}

# Patterns indicating data should NEVER be used for training
TRAINING_EXCLUSION_PATTERNS = [
    r"subject.?id",
    r"patient.?id",
    r"personally.?identifiable",
    r"confidential.?patient",
    r"protected.?health",
]


class SecurityPolicyEngine:
    """
    Deterministic security enforcement engine.

    Validates Teacher recommendations against organizational rules,
    applies redactions, enforces quarantine, and produces audit records.

    This engine NEVER blindly trusts the Teacher. It:
    1. Validates the Teacher's output against known policy rules
    2. ESCALATES (never downgrades) when the Teacher underestimates risk
    3. Applies mandatory redactions regardless of Teacher recommendation
    4. Requires explicit authorization for training data inclusion
    """

    @staticmethod
    def enforce(
        teacher_decision: TeacherDecision,
        user: UserSession,
        content: str,
        training_explicitly_authorized: bool = False,
    ) -> EnforcementResult:
        """
        Apply deterministic Python policy enforcement on top of Teacher recommendations.

        Args:
            teacher_decision: The Teacher LLM's classification and recommendation.
            user: The authenticated user session (role, scopes).
            content: The raw data content being processed.
            training_explicitly_authorized: Whether an authorized officer has explicitly
                approved this data for training use. The Teacher cannot set this alone.

        Returns:
            EnforcementResult with the final, enforced policy decision.
        """
        overrides: List[str] = []
        final_action = teacher_decision.recommended_action
        quarantined = False
        quarantine_reason = None

        # ── Rule 1: Threat Escalation ──
        # If Teacher detected threats, Python ALWAYS escalates to at minimum QUARANTINE
        if teacher_decision.threat_detected:
            if final_action not in ("QUARANTINE", "REJECT"):
                final_action = "QUARANTINE"
                overrides.append(
                    f"ESCALATED: Teacher recommended '{teacher_decision.recommended_action}' "
                    f"but threats were detected — escalated to QUARANTINE."
                )
            quarantined = True
            threat_types = [t.threat_type for t in teacher_decision.threats]
            quarantine_reason = f"Threats detected: {', '.join(threat_types)}"

        # ── Rule 2: Sensitivity-Based Access Control ──
        allowed_roles = SENSITIVITY_ROLE_REQUIREMENTS.get(
            teacher_decision.sensitivity, ["admin"]
        )
        access_granted = user.role in allowed_roles or "*" in user.authorized_scopes

        if not access_granted and final_action == "ALLOW":
            final_action = "RESTRICT"
            overrides.append(
                f"RESTRICTED: User role '{user.role}' lacks access to "
                f"'{teacher_decision.sensitivity}' data."
            )

        # ── Rule 3: Mandatory Redaction ──
        redacted_fields = []
        redacted_content = content

        # Always check mandatory redaction fields regardless of Teacher
        for field in MANDATORY_REDACTION_FIELDS:
            pattern = re.compile(rf"({re.escape(field)})\s*[:=]\s*\S+", re.IGNORECASE)
            if pattern.search(content) and user.role != "admin":
                redacted_content = pattern.sub(f"{field}: [REDACTED]", redacted_content)
                redacted_fields.append(field)

        # Apply Teacher-recommended field redactions for non-admin users
        if user.role != "admin":
            for sf in teacher_decision.sensitive_fields:
                if sf.sensitivity_level in ("HIGHLY_RESTRICTED", "CONFIDENTIAL"):
                    field_name = sf.field_name
                    # Try to redact the field value in the content
                    pattern = re.compile(
                        rf"({re.escape(field_name)})\s*[:=]\s*\S+",
                        re.IGNORECASE,
                    )
                    if pattern.search(redacted_content):
                        redacted_content = pattern.sub(
                            f"{field_name}: [REDACTED]", redacted_content
                        )
                        if field_name not in redacted_fields:
                            redacted_fields.append(field_name)

        if redacted_fields and final_action == "ALLOW":
            final_action = "REDACT"
            if "REDACT" != teacher_decision.recommended_action:
                overrides.append(
                    f"REDACTED: Mandatory sensitive fields detected — "
                    f"redacted {', '.join(redacted_fields)}."
                )

        # ── Rule 4: Training Authorization ──
        # Teacher can RECOMMEND training eligibility, but only explicit human
        # authorization actually permits training use.
        training_authorized = False
        if teacher_decision.training_eligibility == "ELIGIBLE" and training_explicitly_authorized:
            training_authorized = True
        elif teacher_decision.training_eligibility == "NOT_ELIGIBLE":
            training_authorized = False
            if training_explicitly_authorized:
                overrides.append(
                    "BLOCKED: Training was explicitly authorized by a human, but Teacher "
                    "classified data as NOT_ELIGIBLE for training. Requires resolution."
                )
        elif teacher_decision.training_eligibility == "REVIEW_REQUIRED":
            training_authorized = False  # Default deny until human reviews

        # Additional Python-level training exclusion checks
        content_lower = content.lower()
        for pattern in TRAINING_EXCLUSION_PATTERNS:
            if re.search(pattern, content_lower):
                if training_authorized:
                    training_authorized = False
                    overrides.append(
                        f"BLOCKED: Content matches training exclusion pattern "
                        f"'{pattern}'. Training authorization revoked."
                    )

        # ── Rule 5: Never Downgrade Teacher's Severity ──
        action_severity = {
            "ALLOW": 0, "REDACT": 1, "RESTRICT": 2,
            "HUMAN_REVIEW": 3, "QUARANTINE": 4, "REJECT": 5,
        }
        teacher_severity = action_severity.get(teacher_decision.recommended_action, 3)
        final_severity = action_severity.get(final_action, 3)

        if final_severity < teacher_severity:
            # Python should never downgrade Teacher's recommendation
            final_action = teacher_decision.recommended_action
            overrides.append(
                f"RESTORED: Python attempted to downgrade from "
                f"'{teacher_decision.recommended_action}' to a less severe action. "
                f"Teacher recommendation restored."
            )

        # ── Build Enforcement Record ──
        timestamp = datetime.now(timezone.utc).isoformat()
        record_data = {
            "final_action": final_action,
            "teacher_recommendation": teacher_decision.recommended_action,
            "overrides": overrides,
            "timestamp": timestamp,
        }
        enforcement_hash = hashlib.sha256(
            json.dumps(record_data, sort_keys=True).encode()
        ).hexdigest()

        result = EnforcementResult(
            final_action=final_action,
            training_authorized=training_authorized,
            access_granted=access_granted,
            redacted_fields=redacted_fields,
            redacted_content=redacted_content if redacted_fields else None,
            quarantined=quarantined,
            quarantine_reason=quarantine_reason,
            teacher_recommendation=teacher_decision.recommended_action,
            policy_overrides=overrides,
            enforcement_timestamp=timestamp,
            enforcement_hash=enforcement_hash,
        )

        logger.info(
            f"Policy enforcement: teacher_rec={teacher_decision.recommended_action}, "
            f"final={final_action}, access={access_granted}, "
            f"training={training_authorized}, overrides={len(overrides)}"
        )

        return result

    @staticmethod
    def enforce_prompt_security(
        teacher_prompt_analysis: Dict[str, Any],
        user: UserSession,
    ) -> Dict[str, Any]:
        """
        Enforce prompt security policy at inference time.

        Args:
            teacher_prompt_analysis: Teacher's prompt security analysis result.
            user: Authenticated user session.

        Returns:
            Dict with final_action, allowed (bool), and reason.
        """
        overrides = []
        threat_detected = teacher_prompt_analysis.get("threat_detected", False)
        teacher_action = teacher_prompt_analysis.get("recommended_action", "ALLOW")

        final_action = teacher_action

        # Python escalation: if threats detected, always block
        if threat_detected and final_action == "ALLOW":
            final_action = "REJECT"
            overrides.append("ESCALATED: Teacher allowed prompt with detected threats — rejected by Python.")

        # Python check: never downgrade from Teacher's recommendation
        action_severity = {"ALLOW": 0, "RESTRICT": 1, "REJECT": 2}
        if action_severity.get(final_action, 0) < action_severity.get(teacher_action, 0):
            final_action = teacher_action
            overrides.append("RESTORED: Python attempted to downgrade Teacher prompt severity.")

        allowed = (final_action == "ALLOW")

        return {
            "final_action": final_action,
            "allowed": allowed,
            "threat_detected": threat_detected,
            "teacher_recommendation": teacher_action,
            "policy_overrides": overrides,
            "reason": teacher_prompt_analysis.get("reason", ""),
            "enforcement_timestamp": datetime.now(timezone.utc).isoformat(),
        }
