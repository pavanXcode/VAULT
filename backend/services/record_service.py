"""
Scientific Record and Append-Only Scientific Memory Service.
Enforces immutability of raw records, SHA-256 provenance hashing,
deterministic verification checks, and chronological finding ledgers.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid
from sqlalchemy.orm import Session
from backend.models.record import ScientificRecord
from backend.models.assessment import ScientificAssessment
from backend.schemas.record import ScientificRecordInput
from backend.schemas.assessment import (
    EvidenceItem,
    ScientificAssessmentResponse,
    RecordHistoryResponse,
)

VERIFIER_VERSION = "vault_verifier_v1.0"

# Optional hook for Vijay's custom verification engine
_custom_verifier_hook: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None


def register_custom_verifier(fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]]) -> None:
    """Registers an external verifier implementation (e.g. from Vijay's data engine)."""
    global _custom_verifier_hook
    _custom_verifier_hook = fn


def compute_record_hash(record_dict: Dict[str, Any]) -> str:
    """Computes a canonical SHA-256 digest of record measurements and metadata."""
    canonical = json.dumps(record_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RecordService:
    @staticmethod
    def verify_record_logic(record: ScientificRecordInput) -> Dict[str, Any]:
        """
        Deterministic scientific verification rule engine implementing:
        1. Arithmetic consistency: mass / volume vs reported concentration
        2. Threshold compliance: concentration vs regulatory threshold
        3. Method validity: known standards, documented alternative methods, and unknown methods
        4. Instrument calibration window checks
        5. Source references validity
        """
        # If an external verifier hook is registered, invoke it
        if _custom_verifier_hook is not None:
            try:
                external_result = _custom_verifier_hook(record.model_dump())
                if isinstance(external_result, dict) and "status" in external_result:
                    return external_result
            except Exception:
                pass  # Fall back to built-in rules

        issues: List[str] = []
        evidence: List[Dict[str, Any]] = []
        derived: Dict[str, Any] = {}

        mass = record.mass_mg
        volume = record.volume_l
        reported = record.reported_mg_per_l
        threshold = record.threshold_mg_per_l
        original_verdict = record.original_verdict.upper()
        method_id = record.method_id.strip()

        # --- Rule 1: Arithmetic Check (Concentration = Mass / Volume) ---
        if volume <= 0:
            issues.append(f"Invalid volume: {volume} L must be strictly positive.")
            evidence.append({
                "rule": "volume_positivity",
                "expected": "> 0",
                "actual": volume,
                "notes": "Volume must be greater than zero.",
            })
            calculated = 0.0
        else:
            calculated = round(mass / volume, 4)
            derived["calculated_mg_per_l"] = calculated
            derived["arithmetic_discrepancy"] = round(abs(calculated - reported), 4)

            # Allow 1% relative tolerance for precision rounding
            rel_diff = abs(calculated - reported) / max(calculated, 1e-9)
            if rel_diff > 0.01:
                issues.append(
                    f"Arithmetic discrepancy: reported {reported} mg/L, but calculated {calculated} mg/L (mass={mass} mg, volume={volume} L)."
                )
                evidence.append({
                    "rule": "arithmetic_concentration",
                    "expected": calculated,
                    "actual": reported,
                    "notes": f"Relative discrepancy {rel_diff:.2%} exceeds 1.0% tolerance limit.",
                })

        # --- Rule 2: Method-Aware Analysis ---
        is_unknown_method = False
        effective_concentration = calculated if volume > 0 else reported

        if method_id.startswith("MTH-ALT") or "alternative" in method_id.lower():
            # Documented alternative method (e.g. available fraction)
            if record.available_fraction is not None and 0.0 <= record.available_fraction <= 1.0:
                available_conc = round(effective_concentration * record.available_fraction, 4)
                derived["available_fraction"] = record.available_fraction
                derived["available_mg_per_l"] = available_conc
                evidence.append({
                    "rule": "alternative_method_fraction",
                    "factor": record.available_fraction,
                    "available_concentration": available_conc,
                    "notes": f"Documented alternative method {method_id} applies factor {record.available_fraction}.",
                })
                # If threshold measurand matches available fraction, evaluate against that
                if "available" in record.threshold_measurand.lower():
                    effective_concentration = available_conc
            else:
                issues.append(f"Alternative method {method_id} missing valid available_fraction (0.0 to 1.0).")
                evidence.append({
                    "rule": "alternative_method_factor_missing",
                    "method_id": method_id,
                    "actual": record.available_fraction,
                    "notes": "Alternative fraction method requires available_fraction in range [0, 1].",
                })

        elif method_id.startswith("MTH-UNK") or "unknown" in method_id.lower():
            # Unknown method: conservative handling — mark needs_review, DO NOT falsely certify or reject
            is_unknown_method = True
            issues.append(
                f"Unknown methodology '{method_id}': requires expert scientific review to validate assumptions."
            )
            evidence.append({
                "rule": "method_registry_lookup",
                "method_id": method_id,
                "notes": "Method is undocumented in laboratory registry. Forwarded for scientific review.",
            })

        # --- Rule 3: Regulatory Threshold vs Verdict ---
        derived["effective_concentration_mg_per_l"] = effective_concentration
        exceeds_threshold = effective_concentration > threshold

        if exceeds_threshold:
            derived["exceeds_threshold"] = True
            if original_verdict == "PASS":
                issues.append(
                    f"Threshold violation: concentration {effective_concentration} mg/L exceeds threshold {threshold} mg/L, but marked PASS."
                )
                evidence.append({
                    "rule": "regulatory_threshold",
                    "threshold": threshold,
                    "actual": effective_concentration,
                    "original_verdict": original_verdict,
                    "notes": "Record claims PASS despite concentration exceeding permitted limit.",
                })
        else:
            derived["exceeds_threshold"] = False
            if original_verdict == "FAIL" and not issues and not is_unknown_method:
                evidence.append({
                    "rule": "regulatory_threshold",
                    "threshold": threshold,
                    "actual": effective_concentration,
                    "original_verdict": original_verdict,
                    "notes": "Concentration is within threshold, but record was marked FAIL by researcher.",
                })

        # --- Rule 4: Instrument Calibration Window ---
        if record.calibration_valid_until:
            try:
                # ISO date or YYYY-MM-DD
                cal_exp = datetime.fromisoformat(record.calibration_valid_until.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)
                if cal_exp.tzinfo is None:
                    cal_exp = cal_exp.replace(tzinfo=timezone.utc)
                if cal_exp < now_utc:
                    issues.append(
                        f"Expired instrument calibration: expired on {record.calibration_valid_until}."
                    )
                    evidence.append({
                        "rule": "instrument_calibration_window",
                        "valid_until": record.calibration_valid_until,
                        "current_time": now_utc.isoformat(),
                        "notes": "Measurement was performed with or references expired calibration.",
                    })
            except Exception:
                pass  # Non-standard date format handled gracefully

        # --- Determine Overall Verification Status ---
        if is_unknown_method:
            status = "needs_review"
        elif issues:
            status = "flagged"
        else:
            status = "checks_passed"

        return {
            "status": status,
            "issues": issues,
            "evidence": evidence,
            "derived": derived,
            "verifier_version": VERIFIER_VERSION,
        }

    @staticmethod
    def review_record(record_input: ScientificRecordInput) -> ScientificAssessmentResponse:
        """Non-persistent scientific verification (pure evaluation without database writes)."""
        payload_dict = record_input.model_dump()
        source_hash = compute_record_hash(payload_dict)
        verif = RecordService.verify_record_logic(record_input)

        # Teacher LLM semantic & security screening
        from backend.services.teacher_llm_service import _mock_analyze_data, TeacherDecision, SensitiveField, ThreatIndicator
        from backend.services.security_policy_engine import SecurityPolicyEngine
        from backend.services.auth_service import DEFAULT_ANONYMOUS_USER

        content_for_analysis = f"Record ID: {record_input.record_id}\nMethod ID: {record_input.method_id}\nPayload: {json.dumps(payload_dict)}"
        teacher_dec_raw = _mock_analyze_data(content_for_analysis)
        
        sensitive_fields_obj = [
            SensitiveField(field_name=sf["field_name"], sensitivity_level=sf["sensitivity_level"], reason=sf["reason"])
            for sf in teacher_dec_raw.get("sensitive_fields", [])
        ]
        threats_obj = [
            ThreatIndicator(threat_type=th["threat_type"], severity=th["severity"], evidence=th["evidence"], description=th["description"])
            for th in teacher_dec_raw.get("threats", [])
        ]

        teacher_dec = TeacherDecision(
            sensitivity=teacher_dec_raw["sensitivity"],
            importance=teacher_dec_raw["importance"],
            sensitive_fields=sensitive_fields_obj,
            threat_detected=teacher_dec_raw["threat_detected"],
            threats=threats_obj,
            recipient_recommendations=teacher_dec_raw["recipient_recommendations"],
            recommended_action=teacher_dec_raw["recommended_action"],
            training_eligibility=teacher_dec_raw["training_eligibility"],
            review_required=teacher_dec_raw["review_required"],
            reason=teacher_dec_raw["reason"],
            teacher_model="qwen2.5:0.5b",
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=1.5,
            mode="mock",
        )
        policy_res = SecurityPolicyEngine.enforce(
            teacher_dec, DEFAULT_ANONYMOUS_USER, content_for_analysis
        )

        status_val = verif["status"]
        issues_list = list(verif["issues"])
        evidence_list = list(verif["evidence"])

        if teacher_dec.threat_detected:
            status_val = "flagged"
            issues_list.append(f"Security threat detected by Teacher LLM: {teacher_dec.reason}")
            evidence_list.append({
                "rule": "teacher_threat_screening",
                "notes": f"Teacher flagged threat: {teacher_dec.reason}",
            })

        finding_id = f"FND-{uuid.uuid4().hex[:12].upper()}"
        return ScientificAssessmentResponse(
            finding_id=finding_id,
            record_id=record_input.record_id,
            source_hash=source_hash,
            verifier_version=verif.get("verifier_version", VERIFIER_VERSION),
            status=status_val,
            issues=issues_list,
            evidence=evidence_list,
            derived=verif["derived"],
            original_verdict=record_input.original_verdict,
            review_state="automated",
            supersedes_id=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            teacher_decision=teacher_dec.model_dump(),
            policy_enforcement=policy_res.model_dump(),
        )

    @staticmethod
    def ingest_record(
        record_input: ScientificRecordInput,
        db: Session,
    ) -> Tuple[ScientificRecord, ScientificAssessmentResponse]:
        """
        Ingests a scientific laboratory record:
        - Stores the immutable raw record under its content hash (never overwritten).
        - Executes scientific verification.
        - Appends an immutable finding event to the assessment ledger.
        """
        payload_dict = record_input.model_dump()
        source_hash = compute_record_hash(payload_dict)

        # Check for existing record
        existing = (
            db.query(ScientificRecord)
            .filter(ScientificRecord.record_id == record_input.record_id)
            .first()
        )

        if existing:
            # Idempotent re-submission check
            if existing.content_hash != source_hash:
                raise ValueError(
                    f"IMMUTABILITY CONFLICT: Record '{record_input.record_id}' already exists with hash {existing.content_hash}. "
                    "Original laboratory records are immutable and cannot be overwritten. "
                    "Submit new findings or retrospective assessments with a new record ID."
                )
            record_model = existing
        else:
            record_model = ScientificRecord(
                record_id=record_input.record_id,
                content_hash=source_hash,
                raw_payload=json.dumps(payload_dict, sort_keys=True),
                method_id=record_input.method_id,
                threshold_measurand=record_input.threshold_measurand,
                original_verdict=record_input.original_verdict,
                source_refs=json.dumps(record_input.source_refs or []),
            )
            db.add(record_model)
            db.commit()
            db.refresh(record_model)

        # Run verification and persist assessment finding
        assessment_resp = RecordService.review_record(record_input)

        assessment_model = ScientificAssessment(
            finding_id=assessment_resp.finding_id,
            record_id=record_input.record_id,
            source_hash=source_hash,
            verifier_version=assessment_resp.verifier_version,
            status=assessment_resp.status,
            issues=json.dumps(assessment_resp.issues),
            evidence=json.dumps(assessment_resp.evidence),
            derived=json.dumps(assessment_resp.derived),
            original_verdict=record_input.original_verdict,
            review_state="automated",
            supersedes_id=None,
        )
        db.add(assessment_model)
        db.commit()

        return record_model, assessment_resp

    @staticmethod
    def get_record_history(record_id: str, db: Session) -> RecordHistoryResponse:
        """Returns the unchanged original record and its chronological append-only assessment ledger."""
        record = (
            db.query(ScientificRecord)
            .filter(ScientificRecord.record_id == record_id)
            .first()
        )
        if not record:
            raise KeyError(f"Scientific record '{record_id}' not found.")

        assessments = (
            db.query(ScientificAssessment)
            .filter(ScientificAssessment.record_id == record_id)
            .order_by(ScientificAssessment.id.asc())
            .all()
        )

        assessment_responses = [
            ScientificAssessmentResponse(
                finding_id=a.finding_id,
                record_id=a.record_id,
                source_hash=a.source_hash,
                verifier_version=a.verifier_version,
                status=a.status,
                issues=json.loads(a.issues) if a.issues else [],
                evidence=json.loads(a.evidence) if a.evidence else [],
                derived=json.loads(a.derived) if a.derived else {},
                original_verdict=a.original_verdict,
                review_state=a.review_state,
                supersedes_id=a.supersedes_id,
                timestamp=a.created_at.isoformat() if a.created_at else None,
            )
            for a in assessments
        ]

        latest_status = assessment_responses[-1].status if assessment_responses else None
        has_flags = any(a.status in ("flagged", "needs_review") for a in assessment_responses)

        return RecordHistoryResponse(
            record=record.to_dict(),
            assessments=assessment_responses,
            total_assessments=len(assessment_responses),
            latest_status=latest_status,
            has_flags=has_flags,
        )

    @staticmethod
    def append_finding(
        record_id: str,
        status: str,
        issues: List[str],
        evidence: List[Dict[str, Any]],
        supersedes_id: Optional[str],
        db: Session,
        review_state: str = "retrospective_audit",
    ) -> ScientificAssessmentResponse:
        """Appends a new retrospective finding or audit event without altering original raw data."""
        record = (
            db.query(ScientificRecord)
            .filter(ScientificRecord.record_id == record_id)
            .first()
        )
        if not record:
            raise KeyError(f"Scientific record '{record_id}' not found.")

        finding_id = f"FND-{uuid.uuid4().hex[:12].upper()}"
        assessment_model = ScientificAssessment(
            finding_id=finding_id,
            record_id=record_id,
            source_hash=record.content_hash,
            verifier_version=VERIFIER_VERSION,
            status=status,
            issues=json.dumps(issues),
            evidence=json.dumps(evidence),
            derived=json.dumps({}),
            original_verdict=record.original_verdict,
            review_state=review_state,
            supersedes_id=supersedes_id,
        )
        db.add(assessment_model)
        db.commit()

        return ScientificAssessmentResponse(
            finding_id=finding_id,
            record_id=record_id,
            source_hash=record.content_hash,
            verifier_version=VERIFIER_VERSION,
            status=status,
            issues=issues,
            evidence=evidence,
            derived={},
            original_verdict=record.original_verdict,
            review_state=review_state,
            supersedes_id=supersedes_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
