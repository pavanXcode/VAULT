"""
Local LLM generation endpoint.
Ensures zero data leakage to external cloud APIs and supports configurable local inference.
"""

from fastapi import APIRouter, HTTPException, status
from backend.schemas.llm import LLMGenerateRequest, LLMGenerateResponse
from backend.services.llm_service import LocalLLMClient

router = APIRouter(prefix="/llm", tags=["LLM"])


@router.post(
    "/generate",
    response_model=LLMGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate offline text completion via local LLM",
)
async def generate_completion(payload: LLMGenerateRequest):
    """
    Executes text generation using a local offline LLM service (or offline mock if inference engine is unavailable).
    External cloud APIs (OpenAI, Gemini, Claude, etc.) are strictly prohibited.
    """
    if not payload.prompt and not payload.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'prompt' or 'messages' must be provided.",
        )

    try:
        client = LocalLLMClient()
        response = await client.generate(payload)
        return response
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference generation error: {str(exc)}",
        )
