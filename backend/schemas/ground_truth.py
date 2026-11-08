"""
Pydantic schemas for ground-truth dataset validation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class GroundTruthItem(BaseModel):
    id: Optional[Union[str, int]] = None
    prompt: str = Field(..., description="Evaluation prompt / user query")
    reference_answer: str = Field(..., description="Expected ground-truth answer")
    context: Optional[str] = Field(default=None, description="Source context or document chunk")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional per-sample metadata")


class GroundTruthValidationRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, description="Identifier for this dataset")
    items: List[GroundTruthItem] = Field(..., min_length=1, description="Dataset samples to validate")
    check_duplicates: bool = Field(default=True, description="Detect duplicate prompts")
    check_grounding: bool = Field(default=True, description="Verify reference answer overlaps with context")
    min_prompt_length: int = Field(default=3, description="Minimum allowed prompt character length")
    min_answer_length: int = Field(default=1, description="Minimum allowed answer character length")


class ValidationIssue(BaseModel):
    item_index: int
    field: str
    issue_type: str
    message: str
    severity: str = Field(default="error", description="'error' or 'warning'")


class GroundTruthValidationResponse(BaseModel):
    dataset_name: str
    total_samples: int
    valid_samples: int
    invalid_samples: int
    is_valid: bool
    issues: List[ValidationIssue]
    statistics: Dict[str, Any]
    validated_at: datetime
