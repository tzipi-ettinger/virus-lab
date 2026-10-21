import json
from datetime import date

import pytest

from app.extraction.fake_provider import FIXTURES_DIR
from app.extraction.provider import PageImage
from app.pipeline.assemble import assemble, form_id
from app.pipeline.orient import OrientedPage
from app.rules.engine import apply_rules
from app.schemas.api import FormFields
from app.schemas.extraction import RawExtraction, RawField

READINGS = [
    path
    for path in sorted(FIXTURES_DIR.glob("*.json"))
    if "provider_error" not in path.read_text(encoding="utf-8")
]


def oriented(name: str, *, rotation: int = 0, unresolved: bool = False) -> OrientedPage:
    extraction = RawExtraction.model_validate(
        json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )
    image = PageImage(
        file_id="f1", filename="forms.pdf", page_number=4, rotation=rotation, jpeg=b""
    )
    return OrientedPage(
        extraction=extraction,
        image=image,
        applied_rotation=rotation,
        unresolved=unresolved,
        calls=1,
    )


def test_ids_and_source_come_from_the_page():
    form = assemble(oriented("02_sheba_screenshot_rotated", rotation=90))

    assert form.form_id == form_id("f1", 4) == "f1-p4"
    assert (form.file_id, form.source_file, form.page_number) == ("f1", "forms.pdf", 4)
    assert form.applied_rotation == 90
    assert form.processing_status == "ok"
    assert form.error is None


def test_fields_carry_raw_only_for_the_rules():
    form = assemble(oriented("03_maccabi_three_centrals"))

    national_id = form.fields.national_id
    assert national_id.raw == "11223344"
    assert national_id.value is None
    assert national_id.model_status == "found"
    assert national_id.evidence
    assert national_id.issues == []
    assert not (national_id.needs_review or national_id.corrected or national_id.confirmed)
    assert [item.raw for item in form.central_numbers] == ["937309", "937310", "937311"]
    assert not form.needs_review


def test_every_field_is_copied():
    reading = oriented("04_wolfson_two_centrals").extraction
    form = assemble(oriented("04_wolfson_two_centrals"))

    for name in FormFields.model_fields:
        assert getattr(form.fields, name).raw == getattr(reading, name).value
        assert getattr(form.fields, name).model_status == getattr(reading, name).status
    assert [item.raw for item in form.commitment_numbers] == [
        item.value for item in reading.commitment_numbers
    ]


@pytest.mark.parametrize(
    "name, form_type",
    [("03_maccabi_three_centrals", "hmo_form"), ("06_rosenblatt_no_commitment", "private_lab")],
)
def test_the_form_type_comes_from_the_reading(name, form_type):
    # Not the contract's default "unknown": that now means the model itself said so.
    assert assemble(oriented(name)).form_type == form_type


def test_a_value_the_model_says_is_not_found_goes_to_review():
    # Seen on a sample: a case number returned as a commitment, with status not_found.
    reading = oriented("01_meuhedet_clean")
    contradiction = RawField(value="10982910", status="not_found", evidence="מקרה")
    reading.extraction.commitment_numbers = [contradiction]

    form = apply_rules(assemble(reading), today=date(2026, 10, 18))

    [item] = form.commitment_numbers
    assert (item.raw, item.model_status, item.value) == ("10982910", "unclear", None)
    assert item.needs_review and form.needs_review


def test_unresolved_rotation_flags_the_page():
    assert assemble(oriented("01_meuhedet_clean")).issues == []

    form = assemble(oriented("01_meuhedet_clean", unresolved=True))

    assert [issue.code for issue in form.issues] == ["ROTATION_UNRESOLVED"]


# --- The seam with B's rules: every real reading goes through apply_rules.


@pytest.mark.parametrize("path", READINGS, ids=lambda p: p.stem)
def test_every_reading_runs_through_the_rules(path):
    form = apply_rules(assemble(oriented(path.stem)), today=date(2026, 10, 18))

    assert form.processing_status == "ok"
    assert form.form_type == oriented(path.stem).extraction.form_type  # the rules keep it
    assert form.commitment_numbers  # the rules always leave at least one item


def test_rules_catch_the_misread_id():
    form = apply_rules(assemble(oriented("07_sheba_screenshot_misread")), today=date(2026, 10, 18))

    codes = [issue.code for issue in form.fields.national_id.issues]
    assert "ID_CHECKSUM_INVALID" in codes
    assert form.needs_review


def test_rules_merge_the_maccabi_commitment():
    form = apply_rules(assemble(oriented("03_maccabi_three_centrals")), today=date(2026, 10, 18))

    assert [item.value for item in form.commitment_numbers] == ["50364186"]


def boxed(**fields) -> OrientedPage:
    """A page whose fields carry the given box_2d values; everything else not found."""
    nothing = {"value": None, "status": "not_found", "evidence": None}
    raw = {
        "page_rotation_degrees": 0,
        "form_type": "hmo_form",
        **{name: nothing for name in FormFields.model_fields},
        "central_numbers": [],
        "commitment_numbers": [],
        **fields,
    }
    image = PageImage(file_id="f1", filename="forms.pdf", page_number=4, rotation=0, jpeg=b"")
    return OrientedPage(
        extraction=RawExtraction.model_validate(raw),
        image=image,
        applied_rotation=0,
        unresolved=False,
        calls=1,
    )


def read(value: str, box_2d, status: str = "found") -> dict:
    return {"value": value, "status": status, "evidence": "label", "box_2d": box_2d}


def test_the_box_says_where_and_on_which_page_the_value_was_read():
    form = assemble(boxed(national_id=read("11223344", [100, 600, 130, 820])))

    box = form.fields.national_id.box
    assert (box.page_number, box.top, box.left, box.bottom, box.right) == (4, 100, 600, 130, 820)


def test_every_list_item_gets_its_own_box():
    form = assemble(
        boxed(
            central_numbers=[read("937309", [10, 10, 40, 90]), read("937310", [50, 10, 80, 90])],
            commitment_numbers=[read("50364186", [200, 500, 230, 700])],
        )
    )

    assert [item.box.top for item in form.central_numbers] == [10, 50]
    assert form.commitment_numbers[0].box.left == 500


def test_an_unclear_value_keeps_its_box():
    # Unclear is where the reviewer most needs to look.
    form = assemble(boxed(sender=read("מכ", [300, 300, 330, 400], status="unclear")))

    assert form.fields.sender.box is not None


@pytest.mark.parametrize(
    "box_2d",
    [
        None,
        [100, 600, 130],  # three numbers
        [100, 600, 130, 820, 5],
        [130, 600, 100, 820],  # top below bottom
        [100, 820, 130, 600],  # left right of right
        [100, 600, 100, 820],  # flat
        [-5, 600, 130, 820],  # off the page
        [100, 600, 130, 1200],
    ],
)
def test_a_box_that_isnt_a_rectangle_on_the_page_is_dropped(box_2d):
    form = assemble(boxed(national_id=read("11223344", box_2d)))

    assert form.fields.national_id.raw == "11223344"  # the value itself still counts
    assert form.fields.national_id.box is None


def test_a_value_not_found_has_no_box_even_if_the_model_gave_one():
    nothing = {"value": None, "status": "not_found", "evidence": None, "box_2d": [1, 1, 2, 2]}

    assert assemble(boxed(national_id=nothing)).fields.national_id.box is None


def test_the_rules_keep_the_box():
    form = assemble(boxed(national_id=read("11223344", [100, 600, 130, 820])))

    ruled = apply_rules(form, today=date(2026, 10, 21))

    assert ruled.fields.national_id.value == "011223344"  # normalized
    assert ruled.fields.national_id.box == form.fields.national_id.box


def test_a_reading_from_before_boxes_has_none():
    # Fixtures and cached readings from prompt v5 have no box_2d at all.
    form = assemble(oriented("03_maccabi_three_centrals"))

    assert form.fields.national_id.box is None
    assert all(item.box is None for item in form.central_numbers)
