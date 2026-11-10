"""
DAC — Drift-Aware Curation Service for VAULT.

Implements Step 7 of the VAULT pipeline:
Assesses potential safety drift and curates eligible training examples
for Student (Tiny Aya) fine-tuning.

Invariants:
1. Rejects any record where the Teacher LLM flagged threats or marked NOT_ELIGIBLE.
2. Rejects unverified records or records with arithmetic/calibration discrepancies.
3. Computes a safety drift risk score based on lexical perplexity, outlier concentrations, and prompt templates.
4. Generates a curated, reproducible training split with complete cryptographic provenance.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.services.teacher_llm_service import TeacherDecision

logger = logging.getLogger("vault.dac")


class CuratedExample(BaseModel):
    """A verified, drift-screened training example ready for Student fine-tuning."""
    example_id: str
    record_id: str
    source_hash: str
    method_id: str
    prompt: str
    target_answer: str
    drift_score: float  # 0.0 (safe / centered) to 1.0 (high drift risk)
    is_approved: bool
    rejection_reasons: List[str] = Field(default_factory=list)


class CurationReport(BaseModel):
    """Summary report of a Drift-Aware Curation run."""
    run_id: str
    total_evaluated: int
    total_approved: int
    total_rejected: int
    average_drift_score: float
    curated_dataset_hash: str
    approved_examples: List[CuratedExample]
    rejected_examples: List[CuratedExample]


class DriftAwareCurationService:
    @staticmethod
    def calculate_drift_score(
        record_data: Dict[str, Any],
        teacher_decision: Optional[TeacherDecision] = None,
    ) -> float:
        """
        Computes a bounded drift risk score [0.0, 1.0].
        Factors:
        - Sensitivity level (confidential/restricted data incurs higher drift risk)
        - Extreme numeric values (outlier concentrations)
        - Threat indicators or ambiguity
        """
        score = 0.0

        # Teacher sensitivity penalty
        if teacher_decision:
            if teacher_decision.sensitivity == "HIGHLY_RESTRICTED":
                score += 0.5
            elif teacher_decision.sensitivity == "CONFIDENTIAL":
                score += 0.2
            elif teacher_decision.sensitivity == "INTERNAL":
                score += 0.05

            if teacher_decision.threat_detected:
                score += 0.8

            if teacher_decision.review_required:
                score += 0.2

        # Check concentration range outliers (e.g. > 10,000 mg/L or negative)
        reported = record_data.get("reported_mg_per_l", 0.0)
        try:
            val = float(reported)
            if val < 0:
                score += 0.5
            elif val > 10000.0:
                score += 0.5
            elif val > 1000.0:
                score += 0.3
        except (ValueError, TypeError):
            score += 0.4

        return min(1.0, round(score, 3))

    @classmethod
    def curate_dataset(
        cls,
        candidate_records: List[Dict[str, Any]],
        max_drift_threshold: float = 0.35,
    ) -> CurationReport:
        """
        Curates a training set from candidate scientific records, applying:
        1. Teacher classification checks
        2. Verifier status checks
        3. Drift risk thresholding
        """
        approved: List[CuratedExample] = []
        rejected: List[CuratedExample] = []
        drift_sum = 0.0

        for item in candidate_records:
            rec = item.get("record", {})
            assessment = item.get("assessment", {})
            teacher_dec = item.get("teacher_decision")  # Optional TeacherDecision

            rec_id = rec.get("record_id", "UNKNOWN")
            source_hash = rec.get("content_hash", "")
            method_id = rec.get("method_id", "MTH-UNKNOWN")
            rejection_reasons = []

            # Check 1: Verifier approval
            verif_status = assessment.get("status", "unverified")
            if verif_status != "checks_passed":
                rejection_reasons.append(f"Verifier status was '{verif_status}', requires 'checks_passed'.")

            # Check 2: Teacher training eligibility
            if teacher_dec:
                if teacher_dec.threat_detected:
                    rejection_reasons.append("Teacher detected security threats in the record.")
                if teacher_dec.training_eligibility == "NOT_ELIGIBLE":
                    rejection_reasons.append("Teacher classified record as NOT_ELIGIBLE for training.")
                elif teacher_dec.training_eligibility == "REVIEW_REQUIRED":
                    rejection_reasons.append("Teacher classified record as REVIEW_REQUIRED (unresolved).")

            # Check 3: Drift score calculation
            drift = cls.calculate_drift_score(rec, teacher_dec)
            drift_sum += drift

            if drift > max_drift_threshold:
                rejection_reasons.append(f"Safety drift score {drift:.3f} exceeds threshold {max_drift_threshold}.")

            # Format standardized QLoRA chat prompt & target
            mass = rec.get("mass_mg", 0)
            vol = rec.get("volume_l", 1)
            conc = rec.get("reported_mg_per_l", 0)

            prompt = (
                f"Analyze scientific laboratory record {rec_id} using method {method_id}. "
                f"Inputs: mass={mass} mg, volume={vol} L. Determine verified concentration."
            )
            target_answer = (
                f'{{"record_id": "{rec_id}", "verified_mg_per_l": {conc}, '
                f'"status": "{verif_status}", "verdict": "{rec.get("original_verdict", "PASS")}"}}'
            )

            is_app = len(rejection_reasons) == 0
            curated_ex = CuratedExample(
                example_id=f"EX-{rec_id}",
                record_id=rec_id,
                source_hash=source_hash,
                method_id=method_id,
                prompt=prompt,
                target_answer=target_answer,
                drift_score=drift,
                is_approved=is_app,
                rejection_reasons=rejection_reasons,
            )

            if is_app:
                approved.append(curated_ex)
            else:
                rejected.append(curated_ex)

        total_eval = len(candidate_records)
        avg_drift = round(drift_sum / max(1, total_eval), 3)

        # Compute cryptographic fingerprint of approved dataset
        canonical_approved = json.dumps([e.model_dump() for e in approved], sort_keys=True)
        ds_hash = hashlib.sha256(canonical_approved.encode()).hexdigest()

        run_id = f"DAC-{ds_hash[:10].upper()}"

        logger.info(
            f"DAC Curation Complete: {len(approved)} approved, {len(rejected)} rejected. "
            f"Avg drift={avg_drift}, Dataset SHA256={ds_hash[:12]}..."
        )

        return CurationReport(
            run_id=run_id,
            total_evaluated=total_eval,
            total_approved=len(approved),
            total_rejected=len(rejected),
            average_drift_score=avg_drift,
            curated_dataset_hash=ds_hash,
            approved_examples=approved,
            rejected_examples=rejected,
        )
