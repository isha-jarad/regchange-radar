import pytest

from app.models.enums import ChangeType
from app.services.diff_engine import MAX_PARAGRAPHS, detect_changes, word_diff
from app.services.exceptions import DocumentTooComplexError
from app.services.pdf_extraction import Paragraph


def paras(*texts: str) -> list[Paragraph]:
    return [Paragraph(index=i, page=1, text=text) for i, text in enumerate(texts)]


def summarize(old: list[Paragraph], new: list[Paragraph]):
    result = detect_changes(old, new)
    kinds = [(c.change_type.value, c.old_para_start, c.new_para_start) for c in result.changes]
    return result.unchanged_count, kinds


BASE = paras("A one.", "B two.", "C three.")


@pytest.mark.parametrize(
    ("new_texts", "expected"),
    [
        (("A one.", "B two.", "C three."), (3, [])),
        (("A one.", "B two.", "NEW para.", "C three."), (3, [("insert", None, 2)])),
        (("A one.", "C three."), (2, [("delete", 1, None)])),
        (("A one.", "B changed.", "C three."), (2, [("replace", 1, 1)])),
        # Moved text has no "move" type: it appears as an insertion plus a deletion.
        (("C three.", "A one.", "B two."), (2, [("insert", None, 0), ("delete", 2, None)])),
    ],
    ids=["identical", "insertion", "deletion", "replacement", "reordering"],
)
def test_detects_expected_changes(new_texts, expected):
    assert summarize(BASE, paras(*new_texts)) == expected


def test_empty_old_document_is_one_insertion():
    assert summarize([], paras("A one.")) == (0, [("insert", None, 0)])


def test_empty_new_document_is_one_deletion():
    assert summarize(paras("A one.", "B two."), []) == (0, [("delete", 0, None)])


def test_two_empty_documents_have_no_changes():
    assert summarize([], []) == (0, [])


def test_equal_size_replace_block_is_paired_paragraph_by_paragraph():
    old = paras("A one.", "B two.", "C three.", "D four.")
    new = paras("A one.", "B changed.", "C altered.", "D four.")
    result = detect_changes(old, new)
    assert [c.change_type for c in result.changes] == [ChangeType.REPLACE, ChangeType.REPLACE]
    assert [c.old_text for c in result.changes] == ["B two.", "C three."]


def test_unequal_replace_block_stays_one_change():
    old = paras("A one.", "B two.", "C three.")
    new = paras("A one.", "X new.", "Y new.", "C three.")
    result = detect_changes(old, new)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.change_type == ChangeType.REPLACE
    assert change.old_text == "B two."
    assert change.new_text == "X new.\n\nY new."
    assert (change.new_para_start, change.new_para_end) == (1, 2)


def test_change_records_pages_and_similarity():
    old = [Paragraph(0, 1, "Intro."), Paragraph(1, 2, "Old rule.")]
    new = [Paragraph(0, 1, "Intro."), Paragraph(1, 3, "New rule.")]
    change = detect_changes(old, new).changes[0]
    assert (change.old_page, change.new_page) == (2, 3)
    assert 0.0 < change.similarity < 1.0


def test_positions_are_sequential():
    result = detect_changes(paras("A.", "B.", "C.", "D."), paras("A.", "X.", "C."))
    assert [c.position for c in result.changes] == [0, 1]


def test_guard_rejects_huge_documents():
    too_many = paras(*["x"] * (MAX_PARAGRAPHS + 1))
    with pytest.raises(DocumentTooComplexError):
        detect_changes(too_many, [])


def test_word_diff_reports_only_changed_words():
    removed, added, similarity = word_diff(
        "The sponsor may submit the report within 30 days.",
        "The sponsor shall submit the report within 45 days.",
    )
    assert (removed, added, similarity) == ("may 30", "shall 45", 0.8)


def test_word_diff_ignores_letter_case():
    assert word_diff("The Sponsor shall submit.", "the sponsor SHALL submit.") == ("", "", 1.0)


def test_word_diff_keeps_hyphenated_words_and_decimals_together():
    removed, added, _ = word_diff("Keep follow-up at 4.5 mg.", "Keep follow-up at 5.5 mg.")
    assert (removed, added) == ("4.5", "5.5")