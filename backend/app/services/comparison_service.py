import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Comparison, DocumentChange, ImpactFlag
from app.models.enums import ReviewStatus
from app.services.analysis import analyze
from app.services.impact_rules import CompiledRuleSet
from app.services.pdf_extraction import ExtractedDocument


def create_comparison(
    db: Session,
    *,
    old_doc: ExtractedDocument,
    new_doc: ExtractedDocument,
    old_filename: str,
    new_filename: str,
    old_version_label: str,
    new_version_label: str,
    ruleset: CompiledRuleSet,
) -> Comparison:
    """Analyze two documents and save the whole result in one transaction."""
    result = analyze(old_doc.paragraphs, new_doc.paragraphs, ruleset)

    comparison = Comparison(
        old_version_label=old_version_label,
        new_version_label=new_version_label,
        old_filename=old_filename,
        new_filename=new_filename,
        old_sha256=old_doc.sha256,
        new_sha256=new_doc.sha256,
        old_paragraph_count=result.old_paragraph_count,
        new_paragraph_count=result.new_paragraph_count,
        unchanged_count=result.unchanged_count,
        inserted_count=result.inserted_count,
        deleted_count=result.deleted_count,
        replaced_count=result.replaced_count,
        high_count=result.high_count,
        medium_count=result.medium_count,
        low_count=result.low_count,
        ruleset_version=result.ruleset_version,
    )

    for item in result.changes:
        change = item.change
        comparison.changes.append(
            DocumentChange(
                position=change.position,
                change_type=change.change_type.value,
                old_text=change.old_text,
                new_text=change.new_text,
                old_para_start=change.old_para_start,
                old_para_end=change.old_para_end,
                new_para_start=change.new_para_start,
                new_para_end=change.new_para_end,
                old_page=change.old_page,
                new_page=change.new_page,
                similarity=change.similarity,
                priority=item.priority.value,
                flags=[
                    ImpactFlag(
                        rule_id=flag.rule_id,
                        rule_name=flag.rule_name,
                        priority=flag.priority.value,
                        matched_terms=flag.matched_terms,
                        explanation=flag.explanation,
                    )
                    for flag in item.flags
                ],
            )
        )

    db.add(comparison)
    db.commit()
    return comparison


def get_comparison(db: Session, comparison_id: uuid.UUID) -> Comparison | None:
    """Load one comparison with its changes and flags (three queries, no N+1)."""
    stmt = (
        select(Comparison)
        .where(Comparison.id == comparison_id)
        .options(selectinload(Comparison.changes).selectinload(DocumentChange.flags))
    )
    return db.scalars(stmt).one_or_none()


def list_comparisons(db: Session, *, limit: int, offset: int) -> tuple[list[Comparison], int]:
    """Return one page of comparisons (newest first) and the total count."""
    total = db.scalar(select(func.count()).select_from(Comparison)) or 0
    stmt = (
        select(Comparison)
        .order_by(Comparison.created_at.desc(), Comparison.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt)), total


def update_change_review(
    db: Session,
    comparison_id: uuid.UUID,
    change_id: int,
    *,
    status: ReviewStatus,
    note: str | None,
    note_provided: bool,
) -> DocumentChange | None:
    """Update a change's review status; the note is only touched if note_provided."""
    stmt = (
        select(DocumentChange)
        .where(
            DocumentChange.id == change_id,
            DocumentChange.comparison_id == comparison_id,
        )
        .options(selectinload(DocumentChange.flags))
    )
    change = db.scalars(stmt).one_or_none()
    if change is None:
        return None

    change.review_status = status.value
    change.reviewed_at = None if status == ReviewStatus.PENDING else datetime.now(UTC)
    if note_provided:
        change.review_note = note
    db.commit()
    return change