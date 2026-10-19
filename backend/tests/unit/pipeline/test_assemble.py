import json
from datetime import date

import pytest

from app.extraction.fake_provider import FIXTURES_DIR
from app.extraction.provider import PageImage
from app.pipeline.assemble import assemble, form_id
from app.pipeline.orient import OrientedPage
from app.rules.engine import apply_rules
from app.schemas.api import FormFields
from app.schemas.extraction import RawExtraction

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
