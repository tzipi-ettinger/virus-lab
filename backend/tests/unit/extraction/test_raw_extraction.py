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
