"""What the model returns (RawExtraction). May be partial or unclear.

This model is sent to Gemini as the response schema, so it stays flat and simple:
Gemini rejects some JSON Schema features (an enum of ints, for one). Only
pipeline/assemble.py turns it into the contract in schemas/api.py, so this file
can change with the prompt without touching the rules.

Owner: A
"""

from typing import Literal

from pydantic import BaseModel, Field

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
