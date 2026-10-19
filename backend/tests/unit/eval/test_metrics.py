"""The measurement's numbers (SPEC 12, Dev-B plan B2.3), on a small synthetic ground truth."""

from datetime import date
from pathlib import Path

import pytest

from app.rules.engine import apply_rules
from app.schemas.api import Form
from eval.metrics import (
    PageTiming,
    Row,
    evaluate,
    load_ground_truth,
    match,
    render_markdown,
    rows_from_form,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rules"
HEADER = (
    "source_file,page_number,form_type,first_name,last_name,national_id,"
    "central_numbers,received_date,sender,commitment_number,notes\n"
)


def row(page=1, *, flagged=(), form_type="hmo_form", file="a.pdf", **values):
    base = {
        "national_id": "011223344",
        "central_numbers": frozenset({"948062"}),
        "received_date": "2026-06-18",
        "sender": "מכבי",
        "commitment_number": "0260005102632",
    }
    return Row(
        source_file=file,
        page_number=page,
        form_type=form_type,
        values={**base, **values},
        flagged=frozenset(flagged),
    )


def test_ground_truth_reads_lists_and_empty_cells(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text(
        HEADER + '"a, b.pdf",3,hmo_form,דנה,כהן,011223344,948062;948063,,מכבי,,note\n',
        encoding="utf-8",
    )
    [truth] = load_ground_truth(path)
    assert truth.page == ("a, b.pdf", 3)
    assert truth.values == {
        "national_id": "011223344",
        "central_numbers": frozenset({"948062", "948063"}),
        "received_date": None,
        "sender": "מכבי",
        "commitment_number": None,
    }


def test_the_real_ground_truth_file_loads():
    load_ground_truth(Path(__file__).parents[3] / "eval" / "ground_truth.csv")


def test_rows_from_a_form_are_its_records_with_their_flags():
    form = Form.model_validate_json((FIXTURES / "no_commitment.json").read_text(encoding="utf-8"))
    [record] = rows_from_form(apply_rules(form, today=date(2026, 10, 19)))
    assert record.values["commitment_number"] is None
    assert record.flagged == {"commitment_number"}


def test_matching_pairs_the_same_commitment_first_then_by_order():
    truth = [row(commitment_number="1"), row(commitment_number="2"), row(2), row(3)]
    got = [row(commitment_number="2"), row(commitment_number="9"), row(2), row(2), row(4)]
    result = match(truth, got)

    numbers = [
        (t.values["commitment_number"], g.values["commitment_number"]) for t, g in result.pairs
    ]
    assert numbers[:2] == [("2", "2"), ("1", "9")]
    assert [r.page_number for r in result.missing] == [3]
    assert [r.page_number for r in result.extra] == [2]
    assert result.pages_without_truth == 1  # page 4: read, not measured


def test_a_right_record_scores_full_marks():
    report = evaluate([row()], [row()])
    assert all(s.correct == s.total == 1 for s in report.fields.values())
    assert report.zeros_kept == report.zeros_total == 2  # the ID and the commitment number


def test_a_wrong_value_is_an_error_and_unflagged_unless_sent_to_review():
    truth = [row(1), row(2)]
    got = [
        row(1, national_id="011223345"),
        row(2, national_id="011223345", flagged={"national_id"}),
    ]
    score = evaluate(truth, got).fields["national_id"]

    assert (score.correct, score.total) == (0, 2)
    assert score.unflagged_errors == 1
    assert score.places == ["a.pdf:1"]


def test_an_invented_value_is_an_unflagged_error_and_a_missing_one_lowers_coverage():
    truth = [row(1, commitment_number=None), row(2)]
    got = [row(1), row(2, commitment_number=None, flagged={"commitment_number"})]
    score = evaluate(truth, got).fields["commitment_number"]

    assert score.unflagged_errors == 1  # page 1: read a number that isn't there
    assert (score.read, score.present) == (0, 1)  # page 2: there, not read


def test_central_numbers_compare_as_a_set():
    truth = [row(central_numbers=frozenset({"1", "2"}))]
    assert (
        evaluate(truth, [row(central_numbers=frozenset({"2", "1"}))])
        .fields["central_numbers"]
        .correct
        == 1
    )
    assert (
        evaluate(truth, [row(central_numbers=frozenset({"1"}))]).fields["central_numbers"].correct
        == 0
    )


def test_a_dropped_leading_zero_is_counted():
    report = evaluate([row()], [row(national_id="11223344", flagged={"national_id"})])
    assert (report.zeros_kept, report.zeros_total) == (1, 2)


def test_form_type_is_scored_but_never_unflagged():
    score = evaluate([row()], [row(form_type="lab_report")]).fields["form_type"]
    assert (score.correct, score.unflagged_errors) == (0, 0)


def test_records_and_duplicates_count_only_measured_pages():
    truth = [row(1, commitment_number="1"), row(2, commitment_number="2")]
    got = [row(1, commitment_number="1"), row(2, commitment_number="1"), row(9)]
    report = evaluate(truth, got)
    assert (report.expected_records, report.produced_records) == (2, 2)
    assert report.duplicates == 1


@pytest.mark.parametrize("secret", ["011223345", "0260005102632", "מכבי"])
def test_the_report_has_numbers_and_places_but_no_values(secret):
    truth = [row(1), row(2)]
    got = [row(1, national_id="011223345"), row(3)]
    text = render_markdown(
        evaluate(truth, got, failed_pages=1, timings=[PageTiming(pages=2, seconds=10.0)])
    )
    assert "| ת״ז | 0% (0/1) | 100% (1/1) | 1 |" in text
    assert "a.pdf:1" in text
    assert "רשומות חסרות: a.pdf:2" in text
    assert "ממוצע 5.0 שניות" in text
    assert secret not in text
