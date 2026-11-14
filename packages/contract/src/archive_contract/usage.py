"""The optional usage form a reader may answer before a download: no sign-in, no name or email."""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

Organisation = Literal["university", "government", "nonprofit", "company", "individual", "other"]
Purpose = Literal["research", "teaching", "policy-or-management", "commercial", "personal", "other"]

ORGANISATIONS: tuple[str, ...] = get_args(Organisation)
PURPOSES: tuple[str, ...] = get_args(Purpose)
NOTE_LENGTH = 500


class UsageAnswers(BaseModel):
    """The three questions, each optional. Anything else is refused, so nothing identifying
    can be stored by mistake."""

    model_config = ConfigDict(extra="forbid")

    organisation: Organisation | None = None
    purpose: Purpose | None = None
    note: str | None = PydanticField(default=None, max_length=NOTE_LENGTH)
