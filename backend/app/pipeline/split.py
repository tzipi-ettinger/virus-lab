"""Several forms on one page: where to cut it.

A page sometimes holds two or more separate forms (two scans on one sheet, a
photo of two forms side by side), each turned its own way. The model then reports
a box per form (forms_on_page), and each box is cut out and read as a page of its
own (service.py), so each form gets its own rotation and its own records.

Cutting a single form in two is worse than not cutting: each half loses fields.
So the boxes are used only when they look like separate forms: at least two, each
a real part of the page, and hardly overlapping. Anything else reads the page as
one form, as before.

Owner: A
"""

from dataclasses import dataclass

from app.schemas.extraction import RawExtraction

# Boxes are 0-1000 on each side (Gemini's box_2d).
SCALE = 1000
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


@dataclass(frozen=True)
class FormBox:
    """One form's place on the page, 0-1000, margin included."""

    top: int
    left: int
    bottom: int
    right: int

    @property
    def area(self) -> int:
        return (self.bottom - self.top) * (self.right - self.left)


def form_boxes(extraction: RawExtraction) -> list[FormBox]:
    """The forms to cut the page into, in reading order. Empty: read it as one form."""
    boxes = [box for item in extraction.forms_on_page if (box := _box(item.box_2d))]
    if len(boxes) != len(extraction.forms_on_page) or not 2 <= len(boxes) <= MAX_FORMS:
        return []  # one box the model got wrong makes the others doubtful too
    if any(_overlap(a, b) > MAX_OVERLAP for i, a in enumerate(boxes) for b in boxes[i + 1 :]):
        return []
    # Top to bottom, then right to left (Hebrew). A form whose top is within half
    # the smaller height of another's is on the same row.
    boxes.sort(key=lambda box: (box.top, -box.right))
    rows: list[list[FormBox]] = []
    for box in boxes:
        row = rows[-1] if rows else None
        if row and box.top - row[0].top < min(_height(row[0]), _height(box)) / 2:
            row.append(box)
        else:
            rows.append([box])
    ordered = [box for row in rows for box in sorted(row, key=lambda box: -box.right)]
    return [_with_margin(box) for box in ordered]


def _box(box_2d: list[int]) -> FormBox | None:
    if len(box_2d) != 4:
        return None
    top, left, bottom, right = box_2d
    if not (0 <= top < bottom <= SCALE and 0 <= left < right <= SCALE):
        return None
    if bottom - top < MIN_SIDE or right - left < MIN_SIDE:
        return None
    return FormBox(top=top, left=left, bottom=bottom, right=right)


def _height(box: FormBox) -> int:
    return box.bottom - box.top


def _overlap(a: FormBox, b: FormBox) -> float:
    """The shared area, as a share of the smaller box."""
    height = min(a.bottom, b.bottom) - max(a.top, b.top)
    width = min(a.right, b.right) - max(a.left, b.left)
    if height <= 0 or width <= 0:
        return 0.0
    return height * width / min(a.area, b.area)


def _with_margin(box: FormBox) -> FormBox:
    return FormBox(
        top=max(0, box.top - MARGIN),
        left=max(0, box.left - MARGIN),
        bottom=min(SCALE, box.bottom + MARGIN),
        right=min(SCALE, box.right + MARGIN),
    )
