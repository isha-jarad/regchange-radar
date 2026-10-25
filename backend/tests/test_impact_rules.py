import json

import pytest
from pydantic import ValidationError

from app.models.enums import Priority
from app.services.analysis import analyze
from app.services.impact_rules import (
    RuleSet,
    classify_change,
    get_default_ruleset,
    highest_priority,
    load_ruleset,
)
from app.services.pdf_extraction import Paragraph

RULESET = get_default_ruleset()

VALID_RULE = {
    "id": "R1",
    "name": "Rule",
    "priority": "low",
    "description": "d",
    "terms": ["x"],
}


def paras(*texts: str) -> list[Paragraph]:
    return [Paragraph(index=i, page=1, text=text) for i, text in enumerate(texts)]


def rule_ids(flags) -> list[str]:
    return [flag.rule_id for flag in flags]


def test_default_ruleset_loads():
    assert len(RULESET.rules) == 8
    assert RULESET.version == "2026.1"


def test_may_to_shall_flags_obligation_first_then_permission():
    flags = classify_change("may", "shall", RULESET)
    assert rule_ids(flags) == ["OBLIGATION_LANGUAGE", "PERMISSION_LANGUAGE"]
    assert flags[0].priority == Priority.HIGH
    assert highest_priority(flags) == Priority.HIGH


def test_matching_ignores_letter_case():
    flags = classify_change("", "The sponsor SHALL submit.", RULESET)
    assert flags[0].matched_terms == ["shall"]


def test_longest_phrase_wins():
    flags = classify_change("", "The sponsor shall not submit.", RULESET)
    assert flags[0].matched_terms == ["shall not"]


def test_only_whole_words_match():
    assert classify_change("", "mustard seed", RULESET) == []


def test_no_text_means_no_flags_and_priority_none():
    assert classify_change("", "", RULESET) == []
    assert highest_priority([]) == Priority.NONE


def test_explanation_says_which_side_matched():
    flag = classify_change("may", "shall", RULESET)[0]
    assert "Matched in added text: shall." in flag.explanation
    removed_flag = classify_change("may", "shall", RULESET)[1]
    assert "Matched in removed text: may." in removed_flag.explanation


def test_unchanged_words_do_not_trigger_rules():
    result = analyze(
        paras("The sponsor shall submit the report within 30 days."),
        paras("The sponsor shall submit the report within 45 days."),
        RULESET,
    )
    change = result.changes[0]
    assert rule_ids(change.flags) == ["NUMERIC_VALUE"]
    assert change.priority == Priority.MEDIUM


def test_deleted_and_inserted_passages_are_classified_on_their_whole_text():
    deleted = classify_change("A penalty applies to late submissions.", "", RULESET)
    assert rule_ids(deleted) == ["PENALTY_ENFORCEMENT", "SCOPE_APPLICABILITY"]
    inserted = classify_change("", "Sponsors must retain all records for five years.", RULESET)
    assert rule_ids(inserted) == [
        "OBLIGATION_LANGUAGE",
        "DEADLINE_TIMING",
        "REPORTING_RECORDKEEPING",
    ]


def test_full_analysis_of_a_document_pair():
    old = paras(
        "Scope of this guidance.",
        "The sponsor may submit the report within 30 days.",
        "Definitions are listed in the appendix.",
        "A penalty applies to late submissions.",
        "Contact the office for general questions.",
    )
    new = paras(
        "Scope of this guidance.",
        "The sponsor shall submit the report within 45 days.",
        "Definitions are listed in the appendix.",
        "Contact the office for general questions.",
        "Sponsors must retain all records for five years.",
    )
    result = analyze(old, new, RULESET)

    assert [(a.change.change_type.value, a.priority.value) for a in result.changes] == [
        ("replace", "high"),
        ("delete", "high"),
        ("insert", "high"),
    ]
    assert [rule_ids(a.flags) for a in result.changes] == [
        ["OBLIGATION_LANGUAGE", "PERMISSION_LANGUAGE", "NUMERIC_VALUE"],
        ["PENALTY_ENFORCEMENT", "SCOPE_APPLICABILITY"],
        ["OBLIGATION_LANGUAGE", "DEADLINE_TIMING", "REPORTING_RECORDKEEPING"],
    ]
    assert (
        result.unchanged_count,
        result.inserted_count,
        result.deleted_count,
        result.replaced_count,
        result.high_count,
        result.medium_count,
        result.low_count,
        result.ruleset_version,
    ) == (3, 1, 1, 1, 3, 0, 0, "2026.1")


@pytest.mark.parametrize(
    "override",
    [
        {"priority": "none"},
        {"priority": "urgent"},
        {"terms": [], "patterns": []},
        {"patterns": ["("]},
        {"id": ""},
    ],
    ids=["priority-none", "unknown-priority", "no-terms", "broken-regex", "empty-id"],
)
def test_invalid_rules_are_rejected(override):
    with pytest.raises(ValidationError):
        RuleSet.model_validate({"version": "1", "rules": [{**VALID_RULE, **override}]})


def test_duplicate_rule_ids_are_rejected():
    with pytest.raises(ValidationError):
        RuleSet.model_validate({"version": "1", "rules": [VALID_RULE, VALID_RULE]})


def test_rules_are_configurable_from_a_file(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(
        json.dumps(
            {
                "version": "custom-1",
                "rules": [
                    {
                        "id": "BANANA",
                        "name": "Banana",
                        "priority": "low",
                        "description": "A banana was mentioned.",
                        "terms": ["banana"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ruleset = load_ruleset(rules_file)
    assert ruleset.version == "custom-1"
    flags = classify_change("", "We like Banana bread.", ruleset)
    assert [(f.rule_id, f.priority) for f in flags] == [("BANANA", Priority.LOW)]