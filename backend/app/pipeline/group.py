"""Pages -> forms: a page without a central number continues the form before it.

The team lead's rule (A1 in #15): a page with a central number starts a new form,
and a page without one that follows a form is a continuation page of that form.

The rule trusts the model to see every sticker, and in the spike it once missed a
central number on a rotated page. Attaching another patient's page to a form is
the worst mistake here, so a page joins only when nothing on it says otherwise:
no commitment number of its own, a rotation that was resolved, and an ID and name
that are absent or the same as the form's. Any doubt (a conflict, an unclear ID or
name, several forms on it or on the page before it, or the page before it failed)
makes it a form of its own, flagged PAGE_GROUPING_UNCERTAIN for a person to check.

A continuation page only fills in what the form's first page lacks: a value read on
the first page is never replaced.

Owner: A
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.extraction.provider import PageImage
from app.rules.engine import apply_rules
from app.rules.issues import make_issue
from app.schemas.api import Form, FormField, FormFields

# The fields that tell one patient from another.
_IDENTITY = ("national_id", "first_name", "last_name")

Placement = Literal["join", "new", "uncertain"]


@dataclass(frozen=True)
class ReadPage:
    """One page the model read."""

    form: Form  # from assemble: what the model read, before the rules
    ruled: Form  # the same page after apply_rules: what the grouping looks at
    image: PageImage  # what the model read (MAX_SIDE_PX)
    saved: PageImage  # the same page, upright, for storage and the preview (SAVE_MAX_SIDE_PX)
    calls: int
    seconds: float

    @property
    def file_id(self) -> str:
        return self.image.file_id


@dataclass(frozen=True)
class FormGroup:
    """A form's pages, first page first, and the form they make together."""

    pages: tuple[ReadPage, ...]
    merged: Form  # before the rules: continuation pages filled in, flags added
    form: Form  # `merged` after apply_rules

    @property
    def images(self) -> list[PageImage]:
        """The images to save, first page first."""
        return [page.saved for page in self.pages]


def place(page: ReadPage, group: FormGroup | None, *, after_failure: bool) -> Placement:
    """Where a page goes. `group` is the open form of the same file, right before it.

    `after_failure`: the page right before this one, in the same file, failed or
    held several forms (split.py): either way there's no telling what it continues.
    """
    if _has_central_number(page.ruled):
        return "new"
    if after_failure:
        return "uncertain"  # it may belong to the page we couldn't read
    if group is None:
        return "new"  # the file's first page: nothing to continue
    if _belongs_to(page, group.form):
        return "join"
    return "uncertain"


def start(page: ReadPage, *, uncertain: bool, today: date) -> FormGroup:
    merged = page.form
    if uncertain:
        issues = [*merged.issues, make_issue("PAGE_GROUPING_UNCERTAIN")]
        merged = merged.model_copy(update={"issues": issues})
    return FormGroup(pages=(page,), merged=merged, form=apply_rules(merged, today=today))


def join(group: FormGroup, page: ReadPage, *, today: date) -> FormGroup:
    first, extra = group.merged, page.form
    fields = {
        name: _fill(getattr(first.fields, name), getattr(extra.fields, name), extra.page_number)
        for name in FormFields.model_fields
    }
    merged = first.model_copy(
        update={
            "fields": FormFields(**fields),
            "continuation_pages": [*first.continuation_pages, extra.page_number],
        }
    )
    return FormGroup(
        pages=(*group.pages, page), merged=merged, form=apply_rules(merged, today=today)
    )


def several_forms(form: Form) -> bool:
    """The page holds several forms that weren't cut apart (assemble): only one was read."""
    return any(issue.code == "SEVERAL_FORMS_ON_PAGE" for issue in form.issues)


def _has_central_number(form: Form) -> bool:
    # "unclear" counts: there is a sticker, even if it can't be read.
    return any(item.model_status != "not_found" for item in form.central_numbers)


def _belongs_to(page: ReadPage, form: Form) -> bool:
    ruled = page.ruled
    if any(item.model_status != "not_found" for item in ruled.commitment_numbers):
        return False  # its own commitment: a form of its own whose sticker was missed
    if any(issue.code == "ROTATION_UNRESOLVED" for issue in ruled.issues):
        return False  # read sideways, so "no central number" can't be trusted
    if several_forms(ruled):
        return False  # a form on it that wasn't read may have a central number
    return all(
        _same_or_absent(getattr(ruled.fields, n), getattr(form.fields, n)) for n in _IDENTITY
    )


def _same_or_absent(field: FormField, form_field: FormField) -> bool:
    """Nothing on the page contradicts the form: absent on the page, or the same."""
    if field.model_status == "not_found":
        return True
    if field.model_status == "unclear" or field.value is None:
        return False  # something is written there, and we can't tell whose
    if form_field.model_status == "not_found":
        return True  # the form has none: this page fills it in
    # The form's own is unclear or invalid (value None): it can't be told apart either.
    return field.value == form_field.value


def _fill(field: FormField, extra: FormField, page_number: int) -> FormField:
    if field.model_status != "not_found" or extra.model_status == "not_found":
        return field
    # Say where it was read: the preview opens on the form's first page.
    evidence = f"עמוד {page_number}: {extra.evidence}" if extra.evidence else f"עמוד {page_number}"
    return extra.model_copy(update={"evidence": evidence})
