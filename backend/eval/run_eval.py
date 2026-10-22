"""Compare pipeline output to ground_truth.csv (SPEC 12, Dev-B plan B2.3).

    cd backend
    .venv\\Scripts\\python.exe -m eval.run_eval "<sample part 1>.pdf" [more files] [--out report.md]

Reads every page with the provider in backend/.env, always behind CachedProvider
when it is Gemini: a page already read with the same model and prompt costs no
quota, so running it again after a rules change is free. Nothing is saved to the
database. The report goes to stdout, and to --out if given.

Owner: B
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.api.extract import get_provider
from app.clock import israel_today
from app.extraction.provider import ExtractionProvider
from app.pipeline.service import ExtractedForm, ExtractionResult, UploadedFile, extract_files
from app.settings import Settings, get_settings
from eval.metrics import (
    PageTiming,
    Row,
    evaluate,
    load_ground_truth,
    render_markdown,
    rows_from_form,
)

GROUND_TRUTH = Path(__file__).with_name("ground_truth.csv")


async def read_files(
    paths: list[Path], provider: ExtractionProvider, settings: Settings
) -> list[ExtractionResult]:
    """One file at a time, like the upload screen, so the page limit is per file."""
    results = []
    for path in paths:
        result = await extract_files(
            [UploadedFile(filename=path.name, data=path.read_bytes())],
            provider,
            today=israel_today(),
            max_bytes=settings.max_file_bytes,
            max_pages=settings.max_pages_per_request,
            max_concurrency=settings.max_concurrency,
        )
        results.append(result)
        if result.quota_exhausted:
            print("The quota ran out: the rest is not measured.", file=sys.stderr)
            break
    return results


def report_for(results: list[ExtractionResult], truth: list[Row]) -> str:
    forms = [extracted for result in results for extracted in result.forms]
    rows = [row for extracted in forms for row in rows_from_form(extracted.form)]
    failed = sum(len(result.failed_pages) for result in results)
    return render_markdown(evaluate(truth, rows, failed_pages=failed, timings=page_timings(forms)))


def page_timings(forms: list[ExtractedForm]) -> list[PageTiming]:
    """One per form, but one for all the forms cut out of a page: it is one page
    uploaded, and the call that found its forms is counted with the first of them."""
    timings: dict[tuple[str, int], PageTiming] = {}
    for extracted in forms:
        form = extracted.form
        key = (form.source_file, form.page_number)  # only forms cut out of a page share one
        seconds = extracted.seconds + (timings[key].seconds if key in timings else 0.0)
        timings[key] = PageTiming(pages=1 + len(form.continuation_pages), seconds=seconds)
    return list(timings.values())


def main(argv: list[str] | None = None, *, provider: ExtractionProvider | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run_eval")
    parser.add_argument("files", nargs="+", type=Path, help="The sample PDFs or images")
    parser.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH)
    parser.add_argument("--out", type=Path, help="Also write the report to this file")
    args = parser.parse_args(argv)

    settings = get_settings()
    if provider is None:
        provider = get_provider(settings.model_copy(update={"extraction_cache": True}))
    truth = load_ground_truth(args.ground_truth)
    results = asyncio.run(read_files(args.files, provider, settings))
    report = report_for(results, truth)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    sys.stdout.buffer.write(report.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
