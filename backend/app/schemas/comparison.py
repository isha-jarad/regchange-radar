import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.enums import ChangeType, Priority, ReviewStatus


class ImpactFlagRead(BaseModel):
    """One deterministic rule that fired on a change, and why."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    rule_name: str
    priority: Priority
    matched_terms: list[str]
    explanation: str


class ChangeRead(BaseModel):
    """One inserted, deleted, or replaced passage, with its impact flags."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    change_type: ChangeType
    old_text: str | None
    new_text: str | None
    old_para_start: int | None
    old_para_end: int | None
    new_para_start: int | None
    new_para_end: int | None
    old_page: int | None
    new_page: int | None
    similarity: float | None
    priority: Priority
    review_status: ReviewStatus
    review_note: str | None
    reviewed_at: datetime | None
    flags: list[ImpactFlagRead]


class ComparisonSummary(BaseModel):
    """A comparison's metadata and summary counts (used in the history list)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    old_version_label: str
    new_version_label: str
    old_filename: str
    new_filename: str
    old_sha256: str
    new_sha256: str
    old_paragraph_count: int
    new_paragraph_count: int
    unchanged_count: int
    inserted_count: int
    deleted_count: int
    replaced_count: int
    high_count: int
    medium_count: int
    low_count: int
    ruleset_version: str
    created_at: datetime


class ComparisonDetail(ComparisonSummary):
    """A full comparison: the summary plus every detected change."""

    changes: list[ChangeRead]

    @computed_field
    @property
    def total_changes(self) -> int:
        return len(self.changes)

    @computed_field
    @property
    def pending_review_count(self) -> int:
        return sum(1 for change in self.changes if change.review_status == ReviewStatus.PENDING)


class ComparisonListResponse(BaseModel):
    """One page of the comparison history."""

    items: list[ComparisonSummary]
    total: int
    limit: int
    offset: int


class ReviewUpdate(BaseModel):
    """Request body for updating the review status of a single change."""

    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatus
    review_note: str | None = Field(default=None, max_length=2000)