"""build_records: one record per commitment, no cross product (SPEC 7.1)."""

from datetime import date

from app.rules.engine import apply_rules
from app.rules.issues import make_issue
from app.rules.records import blocking_fields, build_records

TODAY = date(2026, 10, 18)


def ruled(load_form, name):
    return apply_rules(load_form(name), today=TODAY)


def test_one_record_per_commitment_with_all_central_numbers(load_form):
    records = build_records(ruled(load_form, "multi_values"))
    assert [r.commitment_index for r in records] == [0, 1]
    assert [r.fields.commitment_number.value for r in records] == ["260005102611", "50364186"]
    for record in records:
        assert [c.value for c in record.central_numbers] == ["948062", "948063"]
        assert record.fields.national_id.value == "011223344"


def test_review_flag_follows_each_records_own_commitment(load_form):
    records = build_records(ruled(load_form, "multi_values"))
    assert [r.needs_review for r in records] == [False, True]
    assert [blocking_fields(r.fields, r.central_numbers) for r in records] == [
        [],
        ["commitment_number"],
    ]


def test_no_cross_product(load_form):
    form = ruled(load_form, "multi_values")
    extra = form.commitment_numbers[0].model_copy(update={"raw": "260005102644"})
    form = apply_rules(
        form.model_copy(update={"commitment_numbers": [*form.commitment_numbers, extra]}),
        today=TODAY,
    )
    records = build_records(form)
    assert len(form.central_numbers) == 2
    assert len(records) == 3


def test_form_without_commitment_is_one_flagged_record(load_form):
    records = build_records(ruled(load_form, "no_commitment"))
    assert len(records) == 1
    commitment = records[0].fields.commitment_number
    assert (commitment.value, [i.code for i in commitment.issues]) == (None, ["REQUIRED_MISSING"])
    assert records[0].needs_review is True
    assert blocking_fields(records[0].fields, records[0].central_numbers) == ["commitment_number"]


def test_unclear_form_lists_every_flagged_field(load_form):
    record = build_records(ruled(load_form, "unclear"))[0]
    assert blocking_fields(record.fields, record.central_numbers) == [
        "first_name",
        "last_name",
        "national_id",
        "received_date",
        "sender",
        "central_numbers[0]",
    ]


def test_records_do_not_share_field_objects(load_form):
    first, second = build_records(ruled(load_form, "multi_values"))
    first.fields.national_id.value = "000000018"
    first.central_numbers[0].value = "111111"
    assert second.fields.national_id.value == "011223344"
    assert second.central_numbers[0].value == "948062"


def test_form_level_warning_flags_every_record(load_form):
    form = load_form("multi_values")
    form.issues = [make_issue("ROTATION_UNRESOLVED")]
    records = build_records(apply_rules(form, today=TODAY))
    assert all(r.needs_review for r in records)
    assert all([i.code for i in r.issues] == ["ROTATION_UNRESOLVED"] for r in records)
