"""FormField.box: where the model read a value (field boxes).

Owner: shared
"""

import pytest
from pydantic import ValidationError

from app.schemas.api import FieldBox, FormField

SAVED_BEFORE_BOXES = {
    "raw": "11223344",
    "value": "011223344",
    "model_status": "found",
    "evidence": "ת.ז.",
    "issues": [],
    "needs_review": False,
    "corrected": False,
    "confirmed": False,
}


def test_a_field_saved_before_boxes_still_loads_without_one():
    # Records already in the database have no "box" key in their JSONB.
    assert FormField.model_validate(SAVED_BEFORE_BOXES).box is None


def test_a_box_survives_the_round_trip_through_storage():
    box = {"page_number": 2, "top": 100, "left": 200, "bottom": 150, "right": 400}
    field = FormField.model_validate({**SAVED_BEFORE_BOXES, "box": box})

    again = FormField.model_validate(field.model_dump(mode="json"))

    assert again.box == FieldBox(**box)


@pytest.mark.parametrize("edge", ["top", "left", "bottom", "right"])
@pytest.mark.parametrize("bad", [-1, 1001])
def test_an_edge_outside_the_page_is_refused(edge, bad):
    box = {"page_number": 1, "top": 0, "left": 0, "bottom": 1000, "right": 1000, edge: bad}
    with pytest.raises(ValidationError):
        FieldBox(**box)
