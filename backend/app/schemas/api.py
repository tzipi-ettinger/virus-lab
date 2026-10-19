"""THE CONTRACT - change only in a shared PR.

DRAFT for A1 (docs/GUIDELINES-V2-CHANGES.md, section 4): records replace forms
as the unit of output; validate and export are gone.

- Every field carries: raw, value, model_status, evidence, issues, needs_review,
  corrected, confirmed (SPEC v0.2 sections 7.4 and 9.2). raw never changes.
- IDs are always strings, to keep leading zeros. Dates in `value` are ISO YYYY-MM-DD.
- The server never trusts issues / needs_review from the client: it recomputes them.

Owner: shared
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ModelStatus = Literal["found", "unclear", "not_found"]
Severity = Literal["info", "warning", "error"]
RecordStatus = Literal["pending", "approved"]

# D17 in #15: the form family only. The organization itself is in `sender`, and the
# Hebrew labels live in the UI. Same values as FormType in schemas/extraction.py.
FormType = Literal[
    "hmo_form",
    "hospital_form",
    "hospital_system_screenshot",
    "lab_report",
    "private_lab",
    "government",
    "unknown",
]

# SPEC v0.2 section 8, plus DUPLICATE_RECORD (A4), PAGE_GROUPING_UNCERTAIN (A1 in #15)
# and COMMITMENT_PREFIX_REMOVED (#18).
IssueCode = Literal[
    "FIELD_UNCLEAR",
    "REQUIRED_MISSING",
    "ID_CHECKSUM_INVALID",
    "ID_LENGTH_INVALID",
    "ID_NORMALIZED",
    "ID_PADDED",
    "DATE_INVALID",
    "DATE_OUT_OF_RANGE",
    "SENDER_UNKNOWN",
    "CENTRAL_FORMAT",
    "COMMITMENT_PREFIX",
    "COMMITMENT_PREFIX_REMOVED",
    "ROTATION_UNRESOLVED",
    "DUPLICATE_REMOVED",
    "DUPLICATE_RECORD",
    "PAGE_GROUPING_UNCERTAIN",
    "EXTRACTION_FAILED",
    "INVALID_FILE",
]
# QUOTA_EXHAUSTED: the page was not read because the daily Gemini quota ran out.
ErrorCode = Literal["EXTRACTION_FAILED", "INVALID_FILE", "QUOTA_EXHAUSTED"]


class Issue(BaseModel):
    code: IssueCode
    severity: Severity
    message: str


class FormField(BaseModel):
    """One field, or one item of a list (central numbers, commitment numbers)."""

    raw: str | None
    value: str | None
    model_status: ModelStatus
    evidence: str | None
    issues: list[Issue]
    needs_review: bool
    corrected: bool
    confirmed: bool


class FormFields(BaseModel):
    first_name: FormField
    last_name: FormField
    national_id: FormField
    received_date: FormField
    sender: FormField


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str


# --- Internal: assemble.py -> apply_rules(form) -> build records (SPEC 9.6). Not sent over HTTP.


class Form(BaseModel):
    form_id: str
    file_id: str
    source_file: str
    page_number: int  # the form's first page
    # Later pages of the same file with no central number of their own (A1 in #15).
    continuation_pages: list[int] = Field(default_factory=list)
    processing_status: Literal["ok", "error"]
    error: ErrorInfo | None
    applied_rotation: int
    form_type: FormType = "unknown"
    fields: FormFields
    central_numbers: list[FormField]
    commitment_numbers: list[FormField]
    issues: list[Issue]
    needs_review: bool


# --- Records (one per commitment number, D2)


class RecordFields(FormFields):
    # One commitment per record. A page without one still becomes a record,
    # with an empty commitment_number flagged REQUIRED_MISSING.
    commitment_number: FormField


class Record(BaseModel):
    record_id: str
    page_id: str
    source_file: str
    page_number: int
    continuation_pages: list[int] = Field(
        default_factory=list,
        description="Later pages of the same file that belong to this form. "
        "page_id / page_number are its first page.",
    )
    continuation_page_ids: list[str] = Field(
        default_factory=list,
        description="The page_id of each continuation page, in the order of "
        "continuation_pages. Load its image from /api/v1/pages/{page_id}/image.",
    )
    commitment_index: int
    status: RecordStatus
    version: int = Field(description="Send back on PATCH / approve; a stale one returns 409.")
    form_type: FormType
    fields: RecordFields
    central_numbers: list[FormField]
    issues: list[Issue]
    needs_review: bool
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None


class RecordSummary(BaseModel):
    """A row on the records screen: effective values only, straight from the record table."""

    record_id: str
    page_id: str
    source_file: str
    page_number: int
    commitment_index: int
    status: RecordStatus
    needs_review: bool
    first_name: str | None
    last_name: str | None
    national_id: str | None
    commitment_number: str | None
    central_numbers: list[str]
    sender: str | None
    form_type: FormType
    received_date: str | None
    created_at: datetime
    approved_at: datetime | None


class RecordList(BaseModel):
    items: list[RecordSummary]
    total: int = Field(description="Matches before limit / offset, for paging.")
    limit: int
    offset: int


# --- POST /api/v1/extract


class FileResult(BaseModel):
    file_id: str = Field(description="Generated by the server.")
    filename: str = Field(description="The original name.")
    page_count: int
    status: Literal["ok", "error"]
    error: ErrorInfo | None


class FailedPage(BaseModel):
    """A page whose extraction failed. It is not saved (A7) and is shown as failed (FR-12)."""

    file_id: str
    source_file: str
    page_number: int
    error: ErrorInfo


class ExtractResponse(BaseModel):
    files: list[FileResult]
    records: list[Record] = Field(description="Saved as pending.")
    failed_pages: list[FailedPage]
    quota_exhausted: bool = Field(
        default=False,
        description="The daily quota ran out after some pages were saved: stop sending "
        "files. The unread pages are in failed_pages with QUOTA_EXHAUSTED. When nothing "
        "was saved, extract answers 503 quota_exhausted instead.",
    )


# --- PATCH /api/v1/records/{record_id}


class FieldEdit(BaseModel):
    """Leave a key out to keep it. value: null clears the field.

    Sending a value unsets confirmed (SPEC 7.4).
    """

    value: str | None = None
    confirmed: bool | None = None


class ListItemEdit(BaseModel):
    idx: int | None = Field(
        default=None,
        description="Position of an existing item (keeps its raw). null adds a new item.",
    )
    value: str | None = None
    confirmed: bool | None = None


class RecordFieldsEdit(BaseModel):
    first_name: FieldEdit | None = None
    last_name: FieldEdit | None = None
    national_id: FieldEdit | None = None
    received_date: FieldEdit | None = None
    sender: FieldEdit | None = None
    commitment_number: FieldEdit | None = None


class RecordPatch(BaseModel):
    version: int
    fields: RecordFieldsEdit | None = None
    central_numbers: list[ListItemEdit] | None = Field(
        default=None,
        description="The full new list. Existing items left out are removed.",
    )


class RecordPatchResponse(BaseModel):
    record: Record
    siblings: list[Record] = Field(
        description="Other records of the same form whose shared fields changed too (A3)."
    )


# --- POST /api/v1/records/{record_id}/approve


class ApproveRequest(BaseModel):
    version: int


# --- Auth (Dev-B plan 2.6): users are created only by scripts/create_user.py


class User(BaseModel):
    """The signed-in user, as require_user gives it to the endpoints."""

    id: str
    username: str
    display_name: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


# --- Errors (application/problem+json, SPEC 9.5)


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    blocking_fields: list[str] | None = Field(
        default=None,
        description='type "review_required" only: fields still flagged, e.g. "national_id", '
        '"central_numbers[1]".',
    )
