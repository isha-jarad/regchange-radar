import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ChangeType, Priority, ReviewStatus, sql_in


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _count_column() -> Mapped[int]:
    return mapped_column(Integer, default=0, server_default="0")


class Comparison(Base):
    """One run of comparing an old document version against a new one."""

    __tablename__ = "comparisons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # What was compared (metadata only; the PDFs themselves are not stored)
    old_version_label: Mapped[str] = mapped_column(String(100))
    new_version_label: Mapped[str] = mapped_column(String(100))
    old_filename: Mapped[str] = mapped_column(String(255))
    new_filename: Mapped[str] = mapped_column(String(255))
    old_sha256: Mapped[str] = mapped_column(String(64))
    new_sha256: Mapped[str] = mapped_column(String(64))

    # Summary counts (paragraph-level)
    old_paragraph_count: Mapped[int] = _count_column()
    new_paragraph_count: Mapped[int] = _count_column()
    unchanged_count: Mapped[int] = _count_column()
    inserted_count: Mapped[int] = _count_column()
    deleted_count: Mapped[int] = _count_column()
    replaced_count: Mapped[int] = _count_column()
    high_count: Mapped[int] = _count_column()
    medium_count: Mapped[int] = _count_column()
    low_count: Mapped[int] = _count_column()

    # Which rule configuration produced the flags (keeps old results explainable)
    ruleset_version: Mapped[str] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), index=True
    )

    changes: Mapped[list["DocumentChange"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
        order_by="DocumentChange.position",
    )


class DocumentChange(Base):
    """One inserted, deleted, or replaced passage found by the comparison."""

    __tablename__ = "document_changes"
    __table_args__ = (
        UniqueConstraint("comparison_id", "position", name="uq_changes_comparison_position"),
        CheckConstraint(sql_in("change_type", ChangeType), name="ck_changes_change_type"),
        CheckConstraint(sql_in("priority", Priority), name="ck_changes_priority"),
        CheckConstraint(sql_in("review_status", ReviewStatus), name="ck_changes_review_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    comparison_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE")
    )
    position: Mapped[int]  # order of this change within the comparison, starting at 0

    change_type: Mapped[str] = mapped_column(String(20))
    old_text: Mapped[str | None] = mapped_column(Text)  # empty for inserts
    new_text: Mapped[str | None] = mapped_column(Text)  # empty for deletes

    # Where the passage sits (paragraph index ranges and first page), for traceability
    old_para_start: Mapped[int | None]
    old_para_end: Mapped[int | None]
    new_para_start: Mapped[int | None]
    new_para_end: Mapped[int | None]
    old_page: Mapped[int | None]
    new_page: Mapped[int | None]

    similarity: Mapped[float | None] = mapped_column(Float)  # 0.0 to 1.0, replaced passages only

    priority: Mapped[str] = mapped_column(
        String(10), default=Priority.NONE.value, server_default=Priority.NONE.value
    )

    review_status: Mapped[str] = mapped_column(
        String(20), default=ReviewStatus.PENDING.value, server_default=ReviewStatus.PENDING.value
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    comparison: Mapped["Comparison"] = relationship(back_populates="changes")
    flags: Mapped[list["ImpactFlag"]] = relationship(
        back_populates="change",
        cascade="all, delete-orphan",
        order_by="ImpactFlag.id",
    )


class ImpactFlag(Base):
    """One deterministic rule that fired on a change, with its explanation."""

    __tablename__ = "impact_flags"
    __table_args__ = (
        CheckConstraint(
            sql_in("priority", (Priority.HIGH, Priority.MEDIUM, Priority.LOW)),
            name="ck_flags_priority",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(
        ForeignKey("document_changes.id", ondelete="CASCADE"), index=True
    )

    rule_id: Mapped[str] = mapped_column(String(64))
    rule_name: Mapped[str] = mapped_column(String(120))
    priority: Mapped[str] = mapped_column(String(10))
    matched_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)

    change: Mapped["DocumentChange"] = relationship(back_populates="flags")