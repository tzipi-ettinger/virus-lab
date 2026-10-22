import pytest

from app.pipeline.split import MARGIN, MAX_FORMS, FormBox, form_boxes
from app.schemas.extraction import RawExtraction, RawField

EMPTY = RawField(value=None, status="not_found", evidence=None)
TOP_HALF = [20, 30, 480, 970]
BOTTOM_HALF = [520, 30, 980, 970]


def reading(*boxes) -> RawExtraction:
    return RawExtraction(
        page_rotation_degrees=0,
        form_type="hmo_form",
        first_name=EMPTY,
        last_name=EMPTY,
        national_id=EMPTY,
        received_date=EMPTY,
        sender=EMPTY,
        central_numbers=[],
        commitment_numbers=[],
        forms_on_page=[{"box_2d": box} for box in boxes],
    )


def test_one_form_or_none_reported_is_read_as_one_form():
    assert form_boxes(reading()) == []
    assert form_boxes(reading(TOP_HALF)) == []


def test_two_forms_one_above_the_other_top_first_with_a_margin():
    boxes = form_boxes(reading(BOTTOM_HALF, TOP_HALF))

    assert boxes == [
        FormBox(top=20 - MARGIN, left=30 - MARGIN, bottom=480 + MARGIN, right=970 + MARGIN),
        FormBox(top=520 - MARGIN, left=30 - MARGIN, bottom=980 + MARGIN, right=970 + MARGIN),
    ]


def test_side_by_side_forms_are_read_right_to_left():
    left, right = [40, 30, 960, 490], [10, 510, 990, 970]  # the right one starts higher

    boxes = form_boxes(reading(left, right))

    assert [box.left for box in boxes] == [510 - MARGIN, 30 - MARGIN]


def test_the_margin_never_leaves_the_page():
    [first, _] = form_boxes(reading([0, 0, 500, 1000], [500, 0, 1000, 1000]))

    assert (first.top, first.left, first.right) == (0, 0, 1000)


@pytest.mark.parametrize(
    "boxes",
    [
        pytest.param([TOP_HALF, [100, 100, 150, 300]], id="a sticker is not a form"),
        pytest.param([TOP_HALF, [10, 30, 600, 970]], id="boxes overlap: one form"),
        pytest.param([TOP_HALF, [520, 30, 980]], id="a box with 3 numbers"),
        pytest.param([TOP_HALF, [980, 30, 520, 970]], id="upside down box"),
        pytest.param([TOP_HALF, [520, 30, 980, 1200]], id="off the page"),
        pytest.param(
            [[i * 200, 0, i * 200 + 200, 1000] for i in range(MAX_FORMS + 1)], id="too many"
        ),
    ],
)
def test_doubtful_boxes_read_the_page_as_one_form(boxes):
    assert form_boxes(reading(*boxes)) == []


def test_up_to_max_forms_are_cut():
    boxes = [[i * 250, 0, i * 250 + 240, 1000] for i in range(MAX_FORMS)]

    assert len(form_boxes(reading(*boxes))) == MAX_FORMS
