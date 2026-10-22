from dataclasses import dataclass

from app.models.enums import ChangeType, Priority
from app.services.diff_engine import DetectedChange, detect_changes
from app.services.impact_rules import (
    CompiledRuleSet,
    FlagResult,
    classify_change,
    highest_priority,
)
from app.services.pdf_extraction import Paragraph


@dataclass(frozen=True)
class AnalyzedChange:
    change: DetectedChange
    priority: Priority
    flags: list[FlagResult]


@dataclass(frozen=True)
class AnalysisResult:
    """Everything Stage 11 needs to save a comparison. Count names match the database columns."""

    changes: list[AnalyzedChange]
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


def analyze(
    old: list[Paragraph], new: list[Paragraph], ruleset: CompiledRuleSet
) -> AnalysisResult:
    """Detect changes between two documents and classify each one with the rules."""
    diff = detect_changes(old, new)

    analyzed: list[AnalyzedChange] = []
    for change in diff.changes:
        flags = classify_change(change.removed_text, change.added_text, ruleset)
        analyzed.append(AnalyzedChange(change, highest_priority(flags), flags))

    def by_type(kind: ChangeType) -> int:
        return sum(1 for item in analyzed if item.change.change_type == kind)

    def by_priority(level: Priority) -> int:
        return sum(1 for item in analyzed if item.priority == level)

    return AnalysisResult(
        changes=analyzed,
        old_paragraph_count=len(old),
        new_paragraph_count=len(new),
        unchanged_count=diff.unchanged_count,
        inserted_count=by_type(ChangeType.INSERT),
        deleted_count=by_type(ChangeType.DELETE),
        replaced_count=by_type(ChangeType.REPLACE),
        high_count=by_priority(Priority.HIGH),
        medium_count=by_priority(Priority.MEDIUM),
        low_count=by_priority(Priority.LOW),
        ruleset_version=ruleset.version,
    )