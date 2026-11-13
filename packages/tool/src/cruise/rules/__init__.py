"""The quality rules, importable without the command line.

Importing this module registers every rule in `REGISTRY`.
"""

from cruise.rules import fields, package, values
from cruise.rules.registry import (
    QUESTIONS,
    REGISTRY,
    Context,
    Outcome,
    Problem,
    Question,
    Registry,
    Rule,
    RuleResult,
    required_fields,
)

__all__ = [
    "QUESTIONS",
    "REGISTRY",
    "Context",
    "Outcome",
    "Problem",
    "Question",
    "Registry",
    "Rule",
    "RuleResult",
    "fields",
    "package",
    "required_fields",
    "values",
]
