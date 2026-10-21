"""Throwaway experiment (step 0 of field boxes): can Gemini say WHERE each value is?

Same pipeline as production (prompt v5, rotation loop, saved preview image), with one
change: every field also asks for box_2d, the value's bounding box on the page as
[ymin, xmin, ymax, xmax] normalized to 0-1000 (Gemini's native box format). The boxes
are drawn on the image the preview would show, so we can judge them by eye, and the
values are compared to eval/ground_truth.csv to see that asking for boxes didn't
hurt the reading.

Not production code. Every page costs 1-3 requests (rotation loop).

Usage (from backend/):
    .venv/Scripts/python spike/spike_boxes.py --samples "C:/Users/1/Downloads" --out <dir>
    .venv/Scripts/python spike/spike_boxes.py ... --pages 1:9 2:12
"""

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from pathlib import Path

import pymupdf
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extraction.gemini_provider import load_prompt  # noqa: E402
from app.extraction.provider import PageImage  # noqa: E402
from app.pipeline.ingest import SAVE_JPEG_QUALITY, SAVE_MAX_SIDE_PX, split_pages  # noqa: E402
from app.pipeline.orient import extract_upright  # noqa: E402
from app.schemas.extraction import FormType, ModelStatus  # noqa: E402
from app.settings import get_settings  # noqa: E402

DEFAULT_PAGES = [
    "1:9",  # Maccabi: 606/ prefix, "ת.דרישה" distractor
    "2:12",  # Wolfson: the vertical sticker is the commitment number
    "2:18",  # Kaplan: hospital form with a Clalit logo
    "1:25",  # rotated Sheba screenshot: do boxes survive the rotation loop?
    "1:17",  # Rosenblatt: no commitment number
]

SAMPLE_FILES = {
    "1": "התחייבויות - דוגמאות, חלק 1 (PDF).pdf",
    "2": "התחייבויות - דוגמאות, חלק 2 (PDF).pdf",
}

BOX_RULE = """
- box_2d: for every field and every list item that has a value (found or unclear), the
  bounding box of the value itself on this page image (the digits or words, not the
  label next to them), as [ymin, xmin, ymax, xmax] normalized to 0-1000. null when the
  field is not_found.
"""


class BoxedField(BaseModel):
    value: str | None
    status: ModelStatus
    evidence: str | None
    box_2d: list[int] | None


class BoxedExtraction(BaseModel):
    page_rotation_degrees: int
    form_type: FormType
    first_name: BoxedField
    last_name: BoxedField
    national_id: BoxedField
    received_date: BoxedField
    sender: BoxedField
    central_numbers: list[BoxedField]
    commitment_numbers: list[BoxedField]


class BoxProvider:
    """Just enough of GeminiProvider for extract_upright: next key on 429, wait on 503."""

    def __init__(self, clients: list[genai.Client], model: str, prompt: str) -> None:
        self._clients, self._model, self._prompt = clients, model, prompt
        self._key = 0
        self._config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BoxedExtraction,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    async def extract(self, page: PageImage) -> BoxedExtraction:
        contents = [types.Part.from_bytes(data=page.jpeg, mime_type="image/jpeg"), self._prompt]
        for attempt in range(8):
            try:
                started = time.perf_counter()
                async with asyncio.timeout(120):
                    response = await self._clients[self._key].aio.models.generate_content(
                        model=self._model, contents=contents, config=self._config
                    )
                print(f"  call ok ({time.perf_counter() - started:.0f}s, key {self._key + 1})")
                return BoxedExtraction.model_validate_json(response.text)
            except TimeoutError:
                print("  timed out after 120s, trying again")
            except errors.APIError as exc:
                if exc.code == 429 and self._key + 1 < len(self._clients):
                    self._key += 1
                    print(f"  429 -> key {self._key + 1}")
                elif exc.code in (500, 503, 504):
                    print(f"  {exc.code}, waiting 15s")
                    await asyncio.sleep(15)
                else:
                    raise
        raise RuntimeError("gave up after 8 attempts")


COLORS = {
    "first_name": (0.2, 0.6, 0.2),
    "last_name": (0.2, 0.6, 0.2),
    "national_id": (0.0, 0.4, 0.9),
    "received_date": (0.9, 0.5, 0.0),
    "sender": (0.6, 0.2, 0.7),
    "central_numbers": (0.9, 0.1, 0.1),
    "commitment_numbers": (0.0, 0.6, 0.6),
}
LABELS = {
    "first_name": "FN",
    "last_name": "LN",
    "national_id": "ID",
    "received_date": "DATE",
    "sender": "SENDER",
    "central_numbers": "C",
    "commitment_numbers": "COM",
}


def boxed_items(extraction: BoxedExtraction) -> list[tuple[str, str, BoxedField]]:
    items = [
        (name, LABELS[name], getattr(extraction, name))
        for name in ("first_name", "last_name", "national_id", "received_date", "sender")
    ]
    for name in ("central_numbers", "commitment_numbers"):
        for i, item in enumerate(getattr(extraction, name), 1):
            items.append((name, f"{LABELS[name]}{i}", item))
    return items


def draw(jpeg: bytes, extraction: BoxedExtraction, out: Path) -> None:
    with pymupdf.open(stream=jpeg, filetype="jpeg") as img:
        rect = img[0].rect
        doc = pymupdf.open()
        page = doc.new_page(width=rect.width, height=rect.height)
        page.insert_image(rect, stream=jpeg)
        for name, label, item in boxed_items(extraction):
            if not item.box_2d or len(item.box_2d) != 4:
                continue
            ymin, xmin, ymax, xmax = item.box_2d
            box = pymupdf.Rect(
                xmin / 1000 * rect.width,
                ymin / 1000 * rect.height,
                xmax / 1000 * rect.width,
                ymax / 1000 * rect.height,
            )
            page.draw_rect(box, color=COLORS[name], width=3)
            page.insert_text((box.x0, max(box.y0 - 4, 10)), label, fontsize=14, color=COLORS[name])
        page.get_pixmap().save(out)


def ground_truth(samples: Path) -> dict[tuple[str, int], dict]:
    path = Path(__file__).resolve().parents[1] / "eval" / "ground_truth.csv"
    with path.open(encoding="utf-8") as f:
        return {(row["source_file"], int(row["page_number"])): row for row in csv.DictReader(f)}


def digits(text: str | None) -> str:
    return re.sub(r"\D", "", text or "")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pages", nargs="*", default=DEFAULT_PAGES)
    parser.add_argument("--key", type=int, default=0, help="index into GEMINI_API_KEYS")
    args = parser.parse_args()

    settings = get_settings()
    keys = settings.gemini_keys()[args.key :]
    clients = [genai.Client(api_key=key.get_secret_value()) for key in keys]
    provider = BoxProvider(clients, settings.gemini_model, load_prompt() + BOX_RULE)
    truth = ground_truth(args.samples)
    args.out.mkdir(parents=True, exist_ok=True)
    results = []

    for spec in args.pages:
        part, number = spec.split(":")
        filename = SAMPLE_FILES[part]
        data = (args.samples / filename).read_bytes()
        pages = split_pages(f"part{part}", filename, data, max_bytes=10**9, max_pages=1000)
        page = pages[int(number) - 1]
        started = time.perf_counter()
        oriented = await extract_upright(provider, page)
        seconds = time.perf_counter() - started
        saved = page.render(
            oriented.applied_rotation, max_side=SAVE_MAX_SIDE_PX, quality=SAVE_JPEG_QUALITY
        )
        extraction: BoxedExtraction = oriented.extraction  # type: ignore[assignment]
        draw(saved.jpeg, extraction, args.out / f"part{part}_p{number}.png")

        gt = truth.get((filename, int(number)), {})
        print(f"\n=== {spec}  rotation {oriented.applied_rotation}  "
              f"{oriented.calls} calls  {seconds:.1f}s")
        for name, label, item in boxed_items(extraction):
            print(f"  {label:7} {item.status:9} {item.value!s:22} box={item.box_2d}")
        checks = {
            "national_id": (digits(extraction.national_id.value), digits(gt.get("national_id"))),
            "central": (
                ";".join(sorted(digits(i.value) for i in extraction.central_numbers)),
                ";".join(sorted(digits(v) for v in (gt.get("central_numbers") or "").split(";"))),
            ),
            "commitment": (
                ";".join(digits((i.value or "").split("/")[-1]) for i in extraction.commitment_numbers),
                digits(gt.get("commitment_number")),
            ),
        }
        for key, (got, want) in checks.items():
            mark = "OK " if got == want else "DIFF"
            print(f"  [{mark}] {key}: got {got!r} want {want!r}")
        results.append(
            {"page": spec, "rotation": oriented.applied_rotation, "calls": oriented.calls,
             "seconds": round(seconds, 1), "extraction": extraction.model_dump()}
        )

    (args.out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nimages and results.json in {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
