"""Can I find, cite and reuse it? The package's own fields."""

from archive_contract.manifest import CORE_FIELDS, Manifest, missing_core_fields
from cruise.rules.registry import Context, Outcome, Problem, rule

CORE_FIXES = {
    "title": "Give the package a title.",
    "description": "Describe the package in at least 50 characters: what, where, when and why.",
    "creator": "Name at least one contributor with the creator role.",
    "rights": "Add a license, or state the rights status if no license can be given.",
    "resources": "Describe at least one resource with a title or description.",
}


def _present(manifest: Manifest, field: str) -> bool:
    """Whether the manifest holds a value for the field, named as in the contract."""
    for name, info in Manifest.model_fields.items():
        if (info.alias or name) == field:
            value = getattr(manifest, name)
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, list):
                return bool(value)
            return value is not None
    raise ValueError(f"no manifest field named {field!r}")


@rule("package.core-missing", question="find", scope="package", severity="error")
def core_missing(ctx: Context) -> Outcome:
    problems = [
        Problem(
            f"The package has no {field}, which every published package needs.",
            values=[field],
            fix=CORE_FIXES[field],
        )
        for field in missing_core_fields(ctx.manifest)
    ]
    return Outcome(problems, len(CORE_FIELDS))


@rule("package.profile-field-missing", question="find", scope="package", severity="error")
def profile_field_missing(ctx: Context) -> Outcome:
    problems = [
        Problem(
            f"The package has no {field}, which the selected profiles or archive config require.",
            values=[field],
            fix=f"Add {field} to the manifest.",
        )
        for field in ctx.required
        if not _present(ctx.manifest, field)
    ]
    return Outcome(problems, len(ctx.required))
