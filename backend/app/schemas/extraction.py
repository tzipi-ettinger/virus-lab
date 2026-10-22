"""What the model returns (RawExtraction). May be partial or unclear.

This model is sent to Gemini as the response schema, so it stays flat and simple:
Gemini rejects some JSON Schema features (an enum of ints, for one). Only
pipeline/assemble.py turns it into the contract in schemas/api.py, so this file
can change with the prompt without touching the rules.

Owner: A
"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
)

ModelStatus = Literal["found", "unclear", "not_found"]

# D17 in issue #15: the form family only. The organization itself is in `sender`.
FormType = Literal[
    "hmo_form",
    "hospital_form",
    "hospital_system_screenshot",
    "lab_report",
    "private_lab",
    "government",
    "unknown",
]


class RawField(BaseModel):
    value: str | None
    status: ModelStatus
    evidence: str | None
    # Gemini's own box format. Default None: readings cached or kept as fixtures
    # before v6 have none. assemble.py drops a box that isn't a rectangle on the page.
    box_2d: list[int] | None = Field(
        default=None,
        description="Bounding box of the value on the page: [ymin, xmin, ymax, xmax], 0-1000.",
    )

    @field_validator("box_2d", mode="wrap")
    @classmethod
    def _box_never_fails_the_page(cls, value: Any, handler: ValidatorFunctionWrapHandler):
        # The box only helps the reviewer look: one that doesn't parse (12.5, "a", a
        # nested list) is dropped, and the values read on the page still count.
        try:
            return handler(value)
        except ValidationError:
            return None


class RawFormBox(BaseModel):
    """Where one separate form lies on the image (two scans on one sheet, say)."""

    box_2d: list[int] = Field(
        description="Bounding box of the whole form: [ymin, xmin, ymax, xmax], 0-1000."
    )


class RawExtraction(BaseModel):
    page_rotation_degrees: int = Field(
        description="Clockwise rotation needed to make the text upright: 0, 90, 180 or 270."
    )
    form_type: FormType
    first_name: RawField
    last_name: RawField
    national_id: RawField
    received_date: RawField
    sender: RawField
    central_numbers: list[RawField]
    commitment_numbers: list[RawField]
    # v8. Default empty: readings cached or kept as fixtures before v8 have none, and
    # empty means one form, as before. pipeline/split.py decides whether to split.
    forms_on_page: list[RawFormBox] = Field(
        default_factory=list,
        description="One item per separate form on the image, when there are two or more.",
    )

    @field_validator("forms_on_page", mode="wrap")
    @classmethod
    def _forms_never_fail_the_page(cls, value: Any, handler: ValidatorFunctionWrapHandler):
        # A list that doesn't parse is read as one form: the fields still count.
        try:
            return handler(value)
        except ValidationError:
            return []


class NamePart(BaseModel):
    """A RawField without a box: the crop's coordinates mean nothing on the page."""

    value: str | None
    status: ModelStatus
    evidence: str | None


class NameReading(BaseModel):
    """The second read of a page: an enlarged crop of the patient's name only
    (pipeline/names.py)."""

    first_name: NamePart
    last_name: NamePart
