"""The command from end to end, with the FakeProvider and a generated PDF (no sample data)."""

import csv
from dataclasses import replace

import pymupdf

from app.extraction.fake_provider import FakeProvider
from eval import run_eval
from eval.metrics import PageTiming

COLUMNS = [
    "source_file",
    "page_number",
    "form_type",
    "first_name",
    "last_name",
    "national_id",
    "central_numbers",
    "received_date",
    "sender",
    "commitment_number",
    "notes",
]


def pdf(path, pages):
    with pymupdf.open() as doc:
        for _ in range(pages):
            doc.new_page(width=595, height=842)
        doc.save(path)
    return path


def test_a_ground_truth_equal_to_the_output_scores_full_marks(tmp_path, capsys):
    """The truth is written from the pipeline's own records: every field is right."""
    path = pdf(tmp_path / "forms.pdf", 3)
    provider = FakeProvider()
    [result] = run_eval.asyncio.run(run_eval.read_files([path], provider, run_eval.get_settings()))
    rows = [
        r
        for f in result.forms
        for r in run_eval.rows_from_form(f.form)
        if r.page_number != 3  # page 3 has no truth yet: read, not measured
    ]
    truth = tmp_path / "gt.csv"
    with truth.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, restval="")
        writer.writeheader()
        for r in rows:
            central = r.values["central_numbers"]
            writer.writerow(
                {
                    "source_file": r.source_file,
                    "page_number": r.page_number,
                    "form_type": r.form_type,
                    **{k: v or "" for k, v in r.values.items() if k != "central_numbers"},
                    "central_numbers": ";".join(sorted(central or [])),
                }
            )

    out = tmp_path / "report.md"
    assert (
        run_eval.main(
            [str(path), "--ground-truth", str(truth), "--out", str(out)], provider=provider
        )
        == 0
    )

    report = out.read_text(encoding="utf-8")
    assert report == capsys.readouterr().out
    assert f"| ת״ז | 100% ({len(rows)}/{len(rows)})" in report
    assert "**שגיאות שלא סומנו, בסך הכול: 0**" in report
    assert "| עמודים בלי טבלת אמת (לא נמדדו) | 1 |" in report


def test_the_forms_cut_out_of_a_page_are_timed_as_one_page(tmp_path):
    path = pdf(tmp_path / "forms.pdf", 1)
    [result] = run_eval.asyncio.run(
        run_eval.read_files([path], FakeProvider(), run_eval.get_settings())
    )
    [form] = result.forms
    page_2 = form.form.model_copy(update={"page_number": 2})
    # Two forms cut out of page 1, the first with the call that found them.
    forms = [replace(form, seconds=3.0), replace(form, seconds=1.0)]

    timings = run_eval.page_timings([*forms, replace(form, form=page_2, seconds=2.0)])

    assert timings == [PageTiming(pages=1, seconds=4.0), PageTiming(pages=1, seconds=2.0)]
