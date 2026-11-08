"""
Ground truth validation service for dataset curation and quality gates.
Enforces standards consistent with CuratorKIT provenance and hallucination checks.
"""

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Dict, List, Set
from sqlalchemy.orm import Session
from backend.models.ground_truth import GroundTruthValidation
from backend.schemas.ground_truth import (
    GroundTruthItem,
    GroundTruthValidationRequest,
    GroundTruthValidationResponse,
    ValidationIssue,
)


def _tokenize_words(text: str) -> Set[str]:
    """Extracts lowercase alphabetic words of length >= 3 for vocabulary checks."""
    return set(re.findall(r"\b[a-zA-Z]{3,}\b", text.lower()))


class GroundTruthService:
    @staticmethod
    def validate_dataset(
        payload: GroundTruthValidationRequest,
        db: Session,
    ) -> GroundTruthValidationResponse:
        """
        Validates ground truth dataset samples:
        - Structural integrity (non-empty prompt, reference_answer)
        - Length constraints
        - Duplicate prompt detection
        - Source context grounding checks
        - Aggregate dataset quality statistics
        """
        issues: List[ValidationIssue] = []
        seen_prompts: Dict[str, int] = {}
        total_samples = len(payload.items)

        total_prompt_len = 0
        total_answer_len = 0
        samples_with_context = 0
        duplicate_count = 0
        invalid_sample_indices = set()

        for idx, item in enumerate(payload.items):
            prompt = item.prompt.strip() if item.prompt else ""
            answer = item.reference_answer.strip() if item.reference_answer else ""
            context = item.context.strip() if item.context else None

            # 1. Check prompt presence and minimum length
            if not prompt:
                issues.append(
                    ValidationIssue(
                        item_index=idx,
                        field="prompt",
                        issue_type="missing_value",
                        message="Prompt cannot be empty.",
                        severity="error",
                    )
                )
                invalid_sample_indices.add(idx)
            elif len(prompt) < payload.min_prompt_length:
                issues.append(
                    ValidationIssue(
                        item_index=idx,
                        field="prompt",
                        issue_type="too_short",
                        message=f"Prompt length ({len(prompt)}) is below minimum {payload.min_prompt_length} characters.",
                        severity="error",
                    )
                )
                invalid_sample_indices.add(idx)

            # 2. Check reference answer presence and minimum length
            if not answer:
                issues.append(
                    ValidationIssue(
                        item_index=idx,
                        field="reference_answer",
                        issue_type="missing_value",
                        message="Reference answer cannot be empty.",
                        severity="error",
                    )
                )
                invalid_sample_indices.add(idx)
            elif len(answer) < payload.min_answer_length:
                issues.append(
                    ValidationIssue(
                        item_index=idx,
                        field="reference_answer",
                        issue_type="too_short",
                        message=f"Answer length ({len(answer)}) is below minimum {payload.min_answer_length} characters.",
                        severity="error",
                    )
                )
                invalid_sample_indices.add(idx)

            # 3. Duplicate prompt check
            if payload.check_duplicates and prompt:
                normalized_prompt = " ".join(prompt.lower().split())
                if normalized_prompt in seen_prompts:
                    original_idx = seen_prompts[normalized_prompt]
                    issues.append(
                        ValidationIssue(
                            item_index=idx,
                            field="prompt",
                            issue_type="duplicate",
                            message=f"Duplicate prompt detected (first seen at index {original_idx}).",
                            severity="warning",
                        )
                    )
                    duplicate_count += 1
                else:
                    seen_prompts[normalized_prompt] = idx

            # 4. Grounding verification against provided context
            if context:
                samples_with_context += 1
                if payload.check_grounding and answer:
                    context_words = _tokenize_words(context)
                    answer_words = _tokenize_words(answer)
                    if answer_words and context_words:
                        overlap = answer_words.intersection(context_words)
                        overlap_ratio = len(overlap) / len(answer_words)
                        if overlap_ratio < 0.15:  # Less than 15% lexical overlap
                            issues.append(
                                ValidationIssue(
                                    item_index=idx,
                                    field="reference_answer",
                                    issue_type="low_grounding",
                                    message=(
                                        f"Low lexical overlap ({overlap_ratio:.1%}) between reference answer "
                                        "and provided source context. Potential ungrounded hallucination."
                                    ),
                                    severity="warning",
                                )
                            )

            total_prompt_len += len(prompt)
            total_answer_len += len(answer)

        invalid_samples = len(invalid_sample_indices)
        valid_samples = total_samples - invalid_samples
        is_valid = invalid_samples == 0

        # Compute deterministic content and verdict digest
        canonical_content = json.dumps(
            [{"p": i.prompt.strip(), "a": i.reference_answer.strip()} for i in payload.items],
            sort_keys=True,
        )
        verdict_hash = hashlib.sha256(f"{canonical_content}:{is_valid}".encode("utf-8")).hexdigest()

        # Check existing historical runs for this dataset to track provenance and detect conflicts
        previous_run = (
            db.query(GroundTruthValidation)
            .filter(GroundTruthValidation.dataset_name == payload.dataset_name)
            .order_by(GroundTruthValidation.id.desc())
            .first()
        )

        conflict_detected = False
        conflict_details = None
        run_sequence = 1

        if previous_run:
            run_sequence = previous_run.run_sequence + 1
            if previous_run.is_valid != is_valid or previous_run.total_samples != total_samples:
                conflict_detected = True
                conflict_details = json.dumps(
                    {
                        "conflict_type": "verdict_discrepancy",
                        "previous_run_id": previous_run.id,
                        "previous_is_valid": previous_run.is_valid,
                        "previous_total_samples": previous_run.total_samples,
                        "new_is_valid": is_valid,
                        "new_total_samples": total_samples,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                issues.append(
                    ValidationIssue(
                        item_index=0,
                        field="dataset_name",
                        issue_type="verdict_conflict",
                        message=(
                            f"Conflicting verdict detected for '{payload.dataset_name}': "
                            f"Previous run #{previous_run.id} was valid={previous_run.is_valid}, "
                            f"current run is valid={is_valid}. Both runs are preserved for provenance audit."
                        ),
                        severity="warning",
                    )
                )

        statistics = {
            "total_samples": total_samples,
            "valid_samples": valid_samples,
            "invalid_samples": invalid_samples,
            "duplicate_prompts_detected": duplicate_count,
            "samples_with_context": samples_with_context,
            "context_coverage_ratio": round(samples_with_context / total_samples, 2) if total_samples else 0.0,
            "avg_prompt_character_length": round(total_prompt_len / total_samples, 1) if total_samples else 0,
            "avg_answer_character_length": round(total_answer_len / total_samples, 1) if total_samples else 0,
            "issues_count_total": len(issues),
            "errors_count": sum(1 for i in issues if i.severity == "error"),
            "warnings_count": sum(1 for i in issues if i.severity == "warning"),
            "verdict_hash": verdict_hash,
            "conflict_detected": conflict_detected,
            "run_sequence": run_sequence,
        }

        # Save record to database with strict provenance (never overwriting existing)
        validation_record = GroundTruthValidation(
            dataset_name=payload.dataset_name,
            total_samples=total_samples,
            valid_samples=valid_samples,
            invalid_samples=invalid_samples,
            is_valid=is_valid,
            issues=json.dumps([i.model_dump() for i in issues]),
            statistics=json.dumps(statistics),
            verdict_hash=verdict_hash,
            rule_engine_version="vijay_rule_engine_v1.0",
            run_sequence=run_sequence,
            conflict_detected=conflict_detected,
            conflict_details=conflict_details,
        )
        db.add(validation_record)
        db.commit()

        return GroundTruthValidationResponse(
            dataset_name=payload.dataset_name,
            total_samples=total_samples,
            valid_samples=valid_samples,
            invalid_samples=invalid_samples,
            is_valid=is_valid,
            issues=issues,
            statistics=statistics,
            validated_at=datetime.now(timezone.utc),
        )
