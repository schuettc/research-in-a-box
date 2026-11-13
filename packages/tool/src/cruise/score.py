"""The completeness score: the share of checks passed, overall and per question."""

from collections.abc import Sequence
from dataclasses import dataclass

from archive_contract.manifest import CheckCount
from cruise.rules import QUESTIONS, Question, RuleResult


@dataclass(frozen=True)
class Score:
    percent: int
    parts: dict[Question, CheckCount]

    def line(self) -> str:
        parts = ", ".join(f"{q} {c.passed} of {c.applicable}" for q, c in self.parts.items())
        return f"{self.percent}% ({parts})"


def completeness(results: Sequence[RuleResult]) -> Score:
    """Checks passed over checks applied, as a whole percent rounded down, with no weights.

    Structure findings come from no rule, so they never reach the score.
    """
    passed = dict.fromkeys(QUESTIONS, 0)
    applicable = dict.fromkeys(QUESTIONS, 0)
    for result in results:
        passed[result.rule.question] += result.passed
        applicable[result.rule.question] += result.checks
    total = sum(applicable.values())
    percent = 100 * sum(passed.values()) // total if total else 100
    parts = {q: CheckCount(passed=passed[q], applicable=applicable[q]) for q in QUESTIONS}
    return Score(percent, parts)
