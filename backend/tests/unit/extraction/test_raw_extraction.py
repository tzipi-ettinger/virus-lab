"""RawField.box_2d: a box that doesn't parse never fails the page (field boxes).

Owner: A
"""

import json

import pytest

from app.schemas.extraction import RawExtraction, RawField

READ = {"value": "11223344", "status": "found", "evidence": "ת.ז."}


@pytest.mark.parametrize("box_2d", [[100, 600, 130, 820], None])
def test_a_box_or_none_is_kept_as_given(box_2d):
    assert RawField.model_validate({**READ, "box_2d": box_2d}).box_2d == box_2d


@pytest.mark.parametrize(
    "box_2d", [[100.5, 600, 130, 820], "100,600,130,820", [[100, 600], [130, 820]], {"y": 1}]
)
def test_a_box_that_doesnt_parse_is_dropped_and_the_value_stays(box_2d):
    field = RawField.model_validate({**READ, "box_2d": box_2d})

    assert field.box_2d is None
    assert field.value == "11223344"


def test_one_bad_box_doesnt_fail_the_whole_answer():
    nothing = {"value": None, "status": "not_found", "evidence": None}
    answer = {
        "page_rotation_degrees": 0,
        "form_type": "hmo_form",
        "first_name": nothing,
        "last_name": nothing,
        "national_id": {**READ, "box_2d": [1.5, "x"]},
        "received_date": nothing,
        "sender": nothing,
        "central_numbers": [],
        "commitment_numbers": [],
    }

    extraction = RawExtraction.model_validate_json(json.dumps(answer))

    assert extraction.national_id.value == "11223344"
    assert extraction.national_id.box_2d is None


def test_the_schema_sent_to_gemini_still_asks_for_a_list_of_ints():
    schema = RawField.model_json_schema()["properties"]["box_2d"]
    assert {"type": "array", "items": {"type": "integer"}} in schema["anyOf"]


# --- forms_on_page (v8: several forms on one image)

NOTHING = {"value": None, "status": "not_found", "evidence": None}
ANSWER = {
    "page_rotation_degrees": 0,
    "form_type": "hmo_form",
    **{name: NOTHING for name in ("first_name", "last_name", "national_id", "received_date")},
    "sender": NOTHING,
    "central_numbers": [],
    "commitment_numbers": [],
}


def test_an_answer_without_forms_on_page_is_one_form():
    # Readings cached or kept as fixtures before v8.
    assert RawExtraction.model_validate(ANSWER).forms_on_page == []


def test_forms_on_page_are_kept_as_given():
    boxes = [{"box_2d": [0, 0, 500, 1000]}, {"box_2d": [500, 0, 1000, 1000]}]

    extraction = RawExtraction.model_validate({**ANSWER, "forms_on_page": boxes})

    assert [item.box_2d for item in extraction.forms_on_page] == [b["box_2d"] for b in boxes]


@pytest.mark.parametrize(
    "forms", [[{"box_2d": [1.5, "x"]}], [{"y": 1}], "two forms", [[0, 0, 500, 1000]]]
)
def test_forms_on_page_that_dont_parse_read_the_page_as_one_form(forms):
    extraction = RawExtraction.model_validate_json(json.dumps({**ANSWER, "forms_on_page": forms}))

    assert extraction.forms_on_page == []
