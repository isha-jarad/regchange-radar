import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Priority

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "rules" / "default_rules.json"

_PRIORITY_ORDER = {Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1, Priority.NONE: 0}


class RuleDefinition(BaseModel):
    """One rule as written in the JSON file."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    priority: Priority
    description: str = Field(min_length=1)
    terms: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_rule(self) -> Self:
        if self.priority == Priority.NONE:
            raise ValueError("a rule's priority must be high, medium, or low")
        if not self.terms and not self.patterns:
            raise ValueError("a rule needs at least one term or pattern")
        for pattern in self.patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
        return self


class RuleSet(BaseModel):
    version: str = Field(min_length=1, max_length=32)
    rules: list[RuleDefinition]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        return self


@dataclass(frozen=True)
class CompiledRule:
    definition: RuleDefinition
    regexes: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class CompiledRuleSet:
    version: str
    rules: tuple[CompiledRule, ...]


@dataclass(frozen=True)
class FlagResult:
    rule_id: str
    rule_name: str
    priority: Priority
    matched_terms: list[str]
    explanation: str


def _compile_rule(rule: RuleDefinition) -> CompiledRule:
    regexes: list[re.Pattern[str]] = []
    if rule.terms:
        # Longest terms first, so "shall not" wins over "shall".
        alternatives = "|".join(
            re.escape(term) for term in sorted(rule.terms, key=len, reverse=True)
        )
        regexes.append(re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE))
    regexes.extend(re.compile(pattern, re.IGNORECASE) for pattern in rule.patterns)
    return CompiledRule(definition=rule, regexes=tuple(regexes))


def load_ruleset(path: Path = DEFAULT_RULES_PATH) -> CompiledRuleSet:
    """Load, validate, and compile a rules file. Raises if the file is invalid."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    ruleset = RuleSet.model_validate(raw)
    return CompiledRuleSet(
        version=ruleset.version,
        rules=tuple(_compile_rule(rule) for rule in ruleset.rules),
    )


@lru_cache
def get_default_ruleset() -> CompiledRuleSet:
    """The built-in ruleset, loaded once per process."""
    return load_ruleset(DEFAULT_RULES_PATH)


def _find_matches(regexes: tuple[re.Pattern[str], ...], text: str) -> list[str]:
    found: list[str] = []
    for regex in regexes:
        for match in regex.finditer(text):
            term = match.group(0).lower()
            if term not in found:
                found.append(term)
    return found


def classify_change(
    removed_text: str, added_text: str, ruleset: CompiledRuleSet
) -> list[FlagResult]:
    """Return every rule that fired on the removed/added text, highest priority first."""
    flags: list[FlagResult] = []
    for rule in ruleset.rules:
        in_added = _find_matches(rule.regexes, added_text)
        in_removed = _find_matches(rule.regexes, removed_text)
        if not in_added and not in_removed:
            continue

        sentences = [rule.definition.description]
        if in_added:
            sentences.append(f"Matched in added text: {', '.join(in_added)}.")
        if in_removed:
            sentences.append(f"Matched in removed text: {', '.join(in_removed)}.")

        flags.append(
            FlagResult(
                rule_id=rule.definition.id,
                rule_name=rule.definition.name,
                priority=rule.definition.priority,
                matched_terms=list(dict.fromkeys(in_added + in_removed)),
                explanation=" ".join(sentences),
            )
        )

    # Stable sort: within one priority, flags keep the order of the rules file.
    flags.sort(key=lambda flag: -_PRIORITY_ORDER[flag.priority])
    return flags


def highest_priority(flags: list[FlagResult]) -> Priority:
    return max(
        (flag.priority for flag in flags),
        key=lambda priority: _PRIORITY_ORDER[priority],
        default=Priority.NONE,
    )