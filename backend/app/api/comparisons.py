import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.comparison import (
    ChangeRead,
    ComparisonDetail,
    ComparisonListResponse,
    ComparisonSummary,
    ReviewUpdate,
)
from app.services import comparison_service
from app.services.exceptions import (
    DocumentError,
    DocumentTooComplexError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from app.services.impact_rules import CompiledRuleSet, get_default_ruleset
from app.services.pdf_extraction import ExtractedDocument, extract_document
from app.services.upload_validation import (
    read_limited,
    safe_display_name,
    validate_pdf_upload,
)

router = APIRouter(prefix="/comparisons", tags=["comparisons"])

VersionLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

UPLOAD_ERRORS = {
    400: {"model": ErrorResponse, "description": "Empty, unreadable, encrypted, or text-less PDF"},
    413: {"model": ErrorResponse, "description": "File exceeds the size limit"},
    415: {"model": ErrorResponse, "description": "File is not a PDF"},
}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Comparison or change not found"}}


def _status_for(exc: DocumentError) -> int:
    if isinstance(exc, FileTooLargeError):
        return 413
    if isinstance(exc, InvalidFileTypeError):
        return 415
    if isinstance(exc, DocumentTooComplexError):
        return 422
    return 400


def _load_document(
    upload: UploadFile, role: str, max_bytes: int
) -> tuple[ExtractedDocument, str]:
    """Validate and extract one upload. `role` ("Old"/"New") is used in error messages."""
    try:
        data = read_limited(upload.file, max_bytes)
        validate_pdf_upload(data, upload.filename)
        document = extract_document(data)
    except DocumentError as exc:
        raise HTTPException(
            status_code=_status_for(exc), detail=f"{role} file: {exc}"
        ) from exc
    return document, safe_display_name(upload.filename, f"{role.lower()}.pdf")


@router.post(
    "",
    response_model=ComparisonDetail,
    status_code=201,
    responses=UPLOAD_ERRORS,
    summary="Compare two versions of a PDF document",
)
def create_comparison(
    old_file: Annotated[UploadFile, File(description="The older version (text-based PDF)")],
    new_file: Annotated[UploadFile, File(description="The newer version (text-based PDF)")],
    old_version_label: Annotated[VersionLabel, Form(description="For example: v1 or 2024-01")],
    new_version_label: Annotated[VersionLabel, Form(description="For example: v2 or 2025-01")],
    db: Annotated[Session, Depends(get_db)],
    ruleset: Annotated[CompiledRuleSet, Depends(get_default_ruleset)],
) -> ComparisonDetail:
    """Detect inserted, deleted, and replaced passages between two PDF versions.

    Each change is flagged high, medium, low, or none by deterministic keyword
    rules, with an explanation of which rule fired. Flags are review aids,
    not legal advice or definitive regulatory decisions.
    """
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    old_doc, old_name = _load_document(old_file, "Old", max_bytes)
    new_doc, new_name = _load_document(new_file, "New", max_bytes)

    try:
        comparison = comparison_service.create_comparison(
            db,
            old_doc=old_doc,
            new_doc=new_doc,
            old_filename=old_name,
            new_filename=new_name,
            old_version_label=old_version_label,
            new_version_label=new_version_label,
            ruleset=ruleset,
        )
    except DocumentError as exc:
        raise HTTPException(status_code=_status_for(exc), detail=str(exc)) from exc
    return ComparisonDetail.model_validate(comparison)


@router.get(
    "",
    response_model=ComparisonListResponse,
    summary="List saved comparisons, newest first",
)
def list_comparisons(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ComparisonListResponse:
    rows, total = comparison_service.list_comparisons(db, limit=limit, offset=offset)
    return ComparisonListResponse(
        items=[ComparisonSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{comparison_id}",
    response_model=ComparisonDetail,
    responses=NOT_FOUND,
    summary="Get one saved comparison with all its changes",
)
def get_comparison(
    comparison_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]
) -> ComparisonDetail:
    comparison = comparison_service.get_comparison(db, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return ComparisonDetail.model_validate(comparison)


@router.patch(
    "/{comparison_id}/changes/{change_id}/review",
    response_model=ChangeRead,
    responses=NOT_FOUND,
    summary="Update the review status of one change",
)
def review_change(
    comparison_id: uuid.UUID,
    change_id: int,
    payload: ReviewUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ChangeRead:
    """Set a change to pending, reviewed, or needs_follow_up, with an optional note.

    The note is only changed when `review_note` is included in the request body.
    """
    change = comparison_service.update_change_review(
        db,
        comparison_id,
        change_id,
        status=payload.review_status,
        note=payload.review_note,
        note_provided="review_note" in payload.model_fields_set,
    )
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return ChangeRead.model_validate(change)