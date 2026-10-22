import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models.enums import ChangeType
from app.services.exceptions import DocumentTooComplexError
from app.services.pdf_extraction import Paragraph

MAX_PARAGRAPHS = 8000

# A word (keeping 4.5, don't, well-known together) or a single punctuation mark.
_TOKEN = re.compile(r"\w+(?:[.,'’\-]\w+)*|[^\w\s]")


@dataclass(frozen=True)
class DetectedChange:
    """One inserted, deleted, or replaced passage. Paragraph ranges are 0-based and inclusive."""

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
    removed_text: str  # words removed (the whole passage, for a deletion)
    added_text: str  # words added (the whole passage, for an insertion)


@dataclass(frozen=True)
class DiffResult:
    changes: list[DetectedChange]
    unchanged_count: int


def word_diff(old_text: str, new_text: str) -> tuple[str, str, float]:
    """Return (removed words, added words, similarity 0-1) between two passages.

    Comparison ignores letter case, so a pure capitalisation change produces no
    removed or added words.
    """
    old_tokens = _TOKEN.findall(old_text)
    new_tokens = _TOKEN.findall(new_text)
    matcher = SequenceMatcher(
        None,
        [t.lower() for t in old_tokens],
        [t.lower() for t in new_tokens],
        autojunk=False,
    )
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend(old_tokens[i1:i2])
        if tag in ("insert", "replace"):
            added.extend(new_tokens[j1:j2])
    return " ".join(removed), " ".join(added), round(matcher.ratio(), 4)


def _join(block: list[Paragraph]) -> str:
    return "\n\n".join(p.text for p in block)


def _build_change(
    position: int, old_block: list[Paragraph], new_block: list[Paragraph]
) -> DetectedChange:
    old_text = _join(old_block) if old_block else None
    new_text = _join(new_block) if new_block else None

    if old_text is not None and new_text is not None:
        change_type = ChangeType.REPLACE
        removed, added, similarity = word_diff(old_text, new_text)
    elif old_text is not None:
        change_type = ChangeType.DELETE
        removed, added, similarity = old_text, "", None
    else:
        change_type = ChangeType.INSERT
        removed, added, similarity = "", new_text or "", None

    return DetectedChange(
        position=position,
        change_type=change_type,
        old_text=old_text,
        new_text=new_text,
        old_para_start=old_block[0].index if old_block else None,
        old_para_end=old_block[-1].index if old_block else None,
        new_para_start=new_block[0].index if new_block else None,
        new_para_end=new_block[-1].index if new_block else None,
        old_page=old_block[0].page if old_block else None,
        new_page=new_block[0].page if new_block else None,
        similarity=similarity,
        removed_text=removed,
        added_text=added,
    )


def detect_changes(old: list[Paragraph], new: list[Paragraph]) -> DiffResult:
    """Compare two paragraph lists and return the changed passages."""
    if len(old) > MAX_PARAGRAPHS or len(new) > MAX_PARAGRAPHS:
        raise DocumentTooComplexError(
            f"Documents with more than {MAX_PARAGRAPHS} paragraphs cannot be compared."
        )

    matcher = SequenceMatcher(
        None, [p.text for p in old], [p.text for p in new], autojunk=False
    )
    changes: list[DetectedChange] = []
    unchanged = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # Same paragraph count on both sides: pair them one-to-one for clearer review.
            for offset in range(i2 - i1):
                changes.append(
                    _build_change(len(changes), [old[i1 + offset]], [new[j1 + offset]])
                )
        else:
            changes.append(_build_change(len(changes), old[i1:i2], new[j1:j2]))

    return DiffResult(changes=changes, unchanged_count=unchanged)