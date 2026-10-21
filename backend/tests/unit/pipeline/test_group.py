from datetime import date

import pytest

from app.extraction.provider import PageImage
from app.pipeline.assemble import assemble
from app.pipeline.group import ReadPage, join, place, start
from app.pipeline.orient import OrientedPage
from app.rules.engine import apply_rules
from app.schemas.extraction import RawExtraction

TODAY = date(2026, 10, 19)
NOTHING = {"value": None, "status": "not_found", "evidence": None}


def found(value: str, evidence: str = "label") -> dict:
    return {"value": value, "status": "found", "evidence": evidence}


UNCLEAR = {"value": None, "status": "unclear", "evidence": "smudged"}

# A first page: central number, commitment, patient and date.
FIRST = {
    "first_name": found("רחל"),
    "last_name": found("כהן"),
    "national_id": found("000000018"),
    "received_date": found("18/10/2026"),
    "sender": found("מכבי"),
    "central_numbers": [found("937309")],
    "commitment_numbers": [found("50364186")],
}


def page(number: int = 1, *, file_id: str = "f1", unresolved: bool = False, **fields) -> ReadPage:
    """A page with only the given fields read; everything else not found."""
    raw = {
        "page_rotation_degrees": 0,
        "form_type": "hmo_form",
        **{name: NOTHING for name in ("first_name", "last_name", "national_id")},
        **{name: NOTHING for name in ("received_date", "sender")},
        "central_numbers": [],
        "commitment_numbers": [],
        **fields,
    }
    extraction = RawExtraction.model_validate(raw)
    image = PageImage(file_id, "forms.pdf", number, 0, f"jpeg {number}".encode())
    oriented = OrientedPage(
        extraction=extraction, image=image, applied_rotation=0, unresolved=unresolved, calls=1
    )
    form = assemble(oriented)
    saved = PageImage(file_id, "forms.pdf", number, 0, f"saved {number}".encode())
    return ReadPage(
        form=form,
        ruled=apply_rules(form, today=TODAY),
        image=image,
        saved=saved,
        calls=1,
        seconds=1.0,
    )


def first_form(**changes):
    return start(page(1, **{**FIRST, **changes}), uncertain=False, today=TODAY)


def test_a_page_with_a_central_number_starts_a_new_form():
    assert place(page(2, **FIRST), first_form(), after_failure=False) == "new"


def test_an_unclear_central_number_still_starts_a_new_form():
    # There is a sticker, even if it can't be read.
    second = page(2, central_numbers=[UNCLEAR])

    assert place(second, first_form(), after_failure=False) == "new"


def test_a_blank_page_after_a_form_continues_it():
    group = first_form()
    second = page(2)

    assert place(second, group, after_failure=False) == "join"
    joined = join(group, second, today=TODAY)
    assert (joined.form.page_number, joined.form.continuation_pages) == (1, [2])
    assert [image.jpeg for image in joined.images] == [b"saved 1", b"saved 2"]  # not the model's
    assert joined.form.issues == []
    assert joined.form.fields.national_id.value == "000000018"


def test_three_pages_make_one_form():
    group = first_form()
    for number in (2, 3):
        group = join(group, page(number), today=TODAY)

    assert group.form.continuation_pages == [2, 3]
    assert len(group.images) == 3


def test_the_same_patient_written_differently_continues_the_form():
    # 00000018 is 000000018 after the rules: compared after normalizing.
    second = page(2, national_id=found("00000018"), first_name=found(" רחל "))

    assert place(second, first_form(), after_failure=False) == "join"


@pytest.mark.parametrize(
    "fields",
    [
        {"national_id": found("000000026")},
        {"first_name": found("שרה")},
        {"last_name": found("לוי")},
    ],
    ids=["other id", "other first name", "other last name"],
)
def test_another_patient_is_never_attached(fields):
    assert place(page(2, **fields), first_form(), after_failure=False) == "uncertain"


def test_an_unclear_id_is_not_attached():
    # Something is written there, and we can't tell whose it is.
    assert place(page(2, national_id=UNCLEAR), first_form(), after_failure=False) == "uncertain"


@pytest.mark.parametrize("first_id", [UNCLEAR, found("12")], ids=["unclear", "invalid"])
def test_an_id_is_not_attached_to_a_form_whose_own_id_cant_be_read(first_id):
    # The form has an ID we can't read, so a readable one can't be shown to match it.
    group = first_form(national_id=first_id)

    assert place(page(2, national_id=found("000000018")), group, after_failure=False) == "uncertain"


def test_a_page_with_its_own_commitment_is_not_attached():
    # Most likely a form of its own whose central-number sticker the model missed.
    second = page(2, commitment_numbers=[found("50364187")])

    assert place(second, first_form(), after_failure=False) == "uncertain"


def test_a_page_read_sideways_is_not_attached():
    assert place(page(2, unresolved=True), first_form(), after_failure=False) == "uncertain"


def test_a_page_after_a_failed_page_is_not_attached():
    # It may belong to the page we couldn't read, not to the form before it.
    assert place(page(3), first_form(), after_failure=True) == "uncertain"
    assert place(page(1), None, after_failure=True) == "uncertain"


def test_the_first_page_of_a_file_without_a_central_number_is_a_plain_new_form():
    assert place(page(1), None, after_failure=False) == "new"


def test_an_uncertain_page_is_flagged_for_review():
    group = start(page(2, national_id=found("000000026")), uncertain=True, today=TODAY)

    assert [issue.code for issue in group.form.issues] == ["PAGE_GROUPING_UNCERTAIN"]
    assert group.form.needs_review
    assert group.form.continuation_pages == []


def test_a_continuation_page_fills_only_what_the_first_page_lacks():
    group = first_form(received_date=NOTHING)
    second = page(
        2,
        received_date=found("19/10/2026", "בחותמת התקבל"),
        sender=found("כללית"),  # the first page already has a sender
    )

    joined = join(group, second, today=TODAY)

    date_field = joined.form.fields.received_date
    assert (date_field.raw, date_field.value) == ("19/10/2026", "2026-10-19")  # the rules ran
    assert date_field.evidence == "עמוד 2: בחותמת התקבל"  # where to look
    assert joined.form.fields.sender.raw == "מכבי"  # never replaced


def test_an_id_found_only_on_the_continuation_page_is_filled_in():
    group = first_form(national_id=NOTHING)

    joined = join(group, page(2, national_id=found("000000018")), today=TODAY)

    assert joined.form.fields.national_id.value == "000000018"


def test_the_next_page_is_compared_with_the_form_so_far():
    # Page 2 gave the form its ID; page 3 with another ID is another patient.
    group = join(
        first_form(national_id=NOTHING), page(2, national_id=found("00000018")), today=TODAY
    )

    assert place(page(3, national_id=found("000000026")), group, after_failure=False) == "uncertain"
    assert place(page(3, national_id=found("000000018")), group, after_failure=False) == "join"


def test_a_value_filled_in_from_a_continuation_page_keeps_that_pages_box():
    # The preview opens on the first page: the box says to turn to page 2.
    group = first_form(received_date=NOTHING)
    stamp = {**found("19/10/2026", "בחותמת התקבל"), "box_2d": [700, 100, 740, 300]}

    joined = join(group, page(2, received_date=stamp), today=TODAY)

    box = joined.form.fields.received_date.box
    assert (box.page_number, box.top, box.left, box.bottom, box.right) == (2, 700, 100, 740, 300)
    assert joined.form.fields.national_id.box is None  # page 1's own reading, read without a box
