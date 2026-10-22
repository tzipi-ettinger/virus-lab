"""Several forms on one page: where to cut it.

A page sometimes holds two or more separate forms (two scans on one sheet, a
photo of two forms side by side), each turned its own way. The model then reports
a box per form (forms_on_page), and each box is cut out and read as a page of its
own (service.py), so each form gets its own rotation and its own records.

Cutting a single form in two is worse than not cutting: each half loses fields.
So the boxes are used only when they look like separate forms: at least two, each
a real part of the page, and hardly overlapping. Anything else reads the page as
one form, flagged for a person (assemble).

No part of the page goes into two cuts. Where two boxes meet (their margins, or
the model's loose edges), each keeps its own side of the middle: a sticker there
is read into one form, never into two patients' records.

Owner: A
"""

from itertools import combinations

from app.pipeline.boxes import SCALE, Box, as_box
from app.schemas.extraction import RawExtraction

# A form is at least this tall and wide: a quarter page is 500 x 500, a sticker
# or a stamp is far smaller.
MIN_SIDE = 200
# More boxes than this is a misreading (sections of one form), and each form costs
# its own model calls.
MAX_FORMS = 4
# Two boxes may share this much of the smaller one's area: the model's edges are loose.
MAX_OVERLAP = 0.2
# Added on every side before cutting, so a loose edge doesn't cut off a number.
MARGIN = 15


def form_boxes(extraction: RawExtraction) -> list[Box]:
    """The forms to cut the page into, in reading order. Empty: read it as one form."""
    boxes = [box for item in extraction.forms_on_page if (box := _form(item.box_2d))]
    if len(boxes) != len(extraction.forms_on_page) or not 2 <= len(boxes) <= MAX_FORMS:
        return []  # one box the model got wrong makes the others doubtful too
    if any(_overlap(a, b) > MAX_OVERLAP for a, b in combinations(boxes, 2)):
        return []
    # Top to bottom, then right to left (Hebrew). A form whose top is within half
    # the smaller height of another's is on the same row.
    boxes.sort(key=lambda box: (box.top, -box.right))
    rows: list[list[Box]] = []
    for box in boxes:
        row = rows[-1] if rows else None
        if row and box.top - row[0].top < min(row[0].height, box.height) / 2:
            row.append(box)
        else:
            rows.append([box])
    ordered = [box for row in rows for box in sorted(row, key=lambda box: -box.right)]
    return _apart([_with_margin(box) for box in ordered])


def _form(box_2d: list[int]) -> Box | None:
    box = as_box(box_2d)
    if box is None or box.height < MIN_SIDE or box.width < MIN_SIDE:
        return None
    return box


def _shared(a: Box, b: Box) -> tuple[int, int]:
    """The height and width of what two boxes share: not positive when nothing."""
    height = min(a.bottom, b.bottom) - max(a.top, b.top)
    width = min(a.right, b.right) - max(a.left, b.left)
    return height, width


def _overlap(a: Box, b: Box) -> float:
    """The shared area, as a share of the smaller box."""
    height, width = _shared(a, b)
    if height <= 0 or width <= 0:
        return 0.0
    return height * width / min(a.height * a.width, b.height * b.width)


def _with_margin(box: Box) -> Box:
    return Box(
        top=max(0, box.top - MARGIN),
        left=max(0, box.left - MARGIN),
        bottom=min(SCALE, box.bottom + MARGIN),
        right=min(SCALE, box.right + MARGIN),
    )


def _apart(boxes: list[Box]) -> list[Box]:
    """The same boxes, each cut back to its own side of the middle of what it shares
    with another: across, for one above the other, or down, for side by side."""
    boxes = list(boxes)
    for i, j in combinations(range(len(boxes)), 2):
        a, b = boxes[i], boxes[j]
        height, width = _shared(a, b)
        if height <= 0 or width <= 0:
            continue
        if height <= width:  # one above the other
            middle = (max(a.top, b.top) + min(a.bottom, b.bottom)) // 2
            upper, lower = (i, j) if a.top + a.bottom <= b.top + b.bottom else (j, i)
            boxes[upper] = boxes[upper]._replace(bottom=middle)
            boxes[lower] = boxes[lower]._replace(top=middle)
        else:  # side by side
            middle = (max(a.left, b.left) + min(a.right, b.right)) // 2
            first, second = (i, j) if a.left + a.right <= b.left + b.right else (j, i)
            boxes[first] = boxes[first]._replace(right=middle)
            boxes[second] = boxes[second]._replace(left=middle)
    return boxes
