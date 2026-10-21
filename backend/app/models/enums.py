from collections.abc import Iterable
from enum import StrEnum


class ChangeType(StrEnum):
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"  # no rule matched; still shown, just not flagged


class ReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    NEEDS_FOLLOW_UP = "needs_follow_up"


def sql_in(column: str, members: Iterable[StrEnum]) -> str:
    """Build a CHECK-constraint expression such as: priority IN ('high', 'low')."""
    values = ", ".join(f"'{member.value}'" for member in members)
    return f"{column} IN ({values})"