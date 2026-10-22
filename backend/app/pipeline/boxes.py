"""A box on a page image in Gemini's box_2d format: top, left, bottom, right, each in
0-1000 of the image, whatever its size.

The model draws them (a field, the name, each form on a page), and ingest draws
parts of a page by them. The one place that knows the format.

Owner: A
"""

from collections.abc import Sequence
from typing import NamedTuple

SCALE = 1000


class Box(NamedTuple):
    top: int
    left: int
    bottom: int
    right: int

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def width(self) -> int:
        return self.right - self.left


WHOLE = Box(0, 0, SCALE, SCALE)


def as_box(value: Sequence[int] | None) -> Box | None:
    """`value` as a Box, or None unless it is a real rectangle on the image: a wrong
    length, an edge off the image or a flat box is dropped, never fixed up, since a
    box in the wrong place is worse than none."""
    if value is None or len(value) != 4:
        return None
    box = Box(*value)
    if not (0 <= box.top < box.bottom <= SCALE and 0 <= box.left < box.right <= SCALE):
        return None
    return box


def turned(box: Box, rotation: int) -> Box:
    """The same place on the image once it is turned `rotation` degrees clockwise."""
    for _ in range(rotation // 90 % 4):
        box = Box(box.left, SCALE - box.bottom, box.right, SCALE - box.top)
    return box
