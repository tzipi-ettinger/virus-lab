"""The measurement of SPEC 12: the pipeline's records against ground_truth.csv.

Pure: rows in, numbers and a Markdown report out. run_eval.py runs the pipeline.
It measures what the rules return, before any person corrects it, and names are
not measured (SPEC 12). The report holds numbers and places (file, page, field),
never the values, so it can go into the README.

Owner: B
"""

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.rules.records import build_records
from app.schemas.api import Form

# What is measured, in the order of the report. "central_numbers" is a list.
FIELDS = ("national_id", "central_numbers", "received_date", "sender", "commitment_number")
FIELD_TITLES = {
    "national_id": "ת״ז",
    "central_numbers": "מספר מרכזי",
    "received_date": "תאריך קבלה",
    "sender": "גורם שולח",
    "commitment_number": "מספר התחייבות",
    "form_type": "סוג טופס",
}
# Identifiers whose leading zeros must survive (SPEC 12).
ZERO_FIELDS = ("national_id", "central_numbers", "commitment_number")

Value = str | frozenset[str] | None


@dataclass(frozen=True)
class Row:
    """One record, from the ground truth or from the pipeline, in comparable form.

    `flagged` is empty for the ground truth: it says which fields the rules sent
    to review.
    """

    source_file: str
    page_number: int
    form_type: str | None
    values: dict[str, Value]
    flagged: frozenset[str] = frozenset()

    @property
    def page(self) -> tuple[str, int]:
        return (self.source_file, self.page_number)


@dataclass(frozen=True)
class PageTiming:
    pages: int
    seconds: float


def _central(text: str | None, sep: str = ";") -> frozenset[str] | None:
    items = frozenset(part.strip() for part in (text or "").split(sep) if part.strip())
    return items or None


def load_ground_truth(path: Path) -> list[Row]:
    """One row per commitment; central numbers separated by ;. Empty = not on the form."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        Row(
            source_file=row["source_file"],
            page_number=int(row["page_number"]),
            form_type=row["form_type"] or None,
            values={
                name: _central(row[name]) if name == "central_numbers" else row[name] or None
                for name in FIELDS
            },
        )
        for row in rows
    ]


def rows_from_form(form: Form) -> list[Row]:
    """The records the system saves for one form, as the rules left them."""
    rows = []
    for draft in build_records(form):
        fields = draft.fields
        flagged = {name for name in FIELDS if name != "central_numbers"}
        flagged = {name for name in flagged if getattr(fields, name).needs_review}
        if any(item.needs_review for item in draft.central_numbers):
            flagged.add("central_numbers")
        values: dict[str, Value] = {
            name: getattr(fields, name).value for name in FIELDS if name != "central_numbers"
        }
        values["central_numbers"] = (
            frozenset(item.value for item in draft.central_numbers if item.value) or None
        )
        rows.append(
            Row(
                source_file=form.source_file,
                page_number=form.page_number,
                form_type=form.form_type,
                values=values,
                flagged=frozenset(flagged),
            )
        )
    return rows


@dataclass
class Matching:
    pairs: list[tuple[Row, Row]] = field(default_factory=list)  # (truth, extracted)
    missing: list[Row] = field(default_factory=list)  # truth rows with no record
    extra: list[Row] = field(default_factory=list)  # records with no truth row
    pages_without_truth: int = 0  # read, but not in the ground truth yet: not measured


def match(truth: list[Row], extracted: list[Row]) -> Matching:
    """Pair records page by page: the same commitment number first, then in order."""
    result = Matching()
    truth_pages = {row.page for row in truth}
    result.pages_without_truth = len({r.page for r in extracted} - truth_pages)
    for page in sorted(truth_pages):
        expected = [row for row in truth if row.page == page]
        got = [row for row in extracted if row.page == page]
        for want in list(expected):
            number = want.values["commitment_number"]
            same = next(
                (g for g in got if number and g.values["commitment_number"] == number), None
            )
            if same:
                result.pairs.append((want, same))
                expected.remove(want)
                got.remove(same)
        result.pairs += list(zip(expected, got, strict=False))
        result.missing += expected[len(got) :]
        result.extra += got[len(expected) :]
    return result


@dataclass
class FieldScore:
    correct: int = 0
    total: int = 0
    present: int = 0  # on the form, by the ground truth
    read: int = 0  # on the form, and the record has a value
    unflagged_errors: int = 0
    places: list[str] = field(default_factory=list)  # file:page of each unflagged error

    def percent(self, part: int, whole: int) -> str:
        return f"{100 * part / whole:.0f}% ({part}/{whole})" if whole else "—"


@dataclass
class Report:
    fields: dict[str, FieldScore]
    expected_records: int
    produced_records: int
    matched: int
    missing: list[str]
    extra: list[str]
    duplicates: int
    pages_without_truth: int
    zeros_kept: int
    zeros_total: int
    failed_pages: int
    timings: list[PageTiming]


def _place(row: Row) -> str:
    return f"{row.source_file}:{row.page_number}"


def evaluate(
    truth: list[Row],
    extracted: list[Row],
    *,
    failed_pages: int = 0,
    timings: list[PageTiming] | None = None,
) -> Report:
    matching = match(truth, extracted)
    scores = {name: FieldScore() for name in (*FIELDS, "form_type")}
    zeros_kept = zeros_total = 0
    for want, got in matching.pairs:
        for name in FIELDS:
            score, expected, actual = scores[name], want.values[name], got.values[name]
            score.total += 1
            score.correct += expected == actual
            if expected is not None:
                score.present += 1
                score.read += actual is not None
            if expected != actual and name not in got.flagged:
                score.unflagged_errors += 1
                score.places.append(_place(want))
            if name in ZERO_FIELDS:
                for value in _zero_values(expected):
                    zeros_total += 1
                    zeros_kept += value in _items(actual)
        type_score = scores["form_type"]
        type_score.total += 1
        type_score.correct += want.form_type == got.form_type

    measured = [row for row in extracted if row.page in {t.page for t in truth}]
    numbers = Counter(
        row.values["commitment_number"] for row in measured if row.values["commitment_number"]
    )
    return Report(
        fields=scores,
        expected_records=len(truth),
        produced_records=len(measured),
        matched=len(matching.pairs),
        missing=[_place(row) for row in matching.missing],
        extra=[_place(row) for row in matching.extra],
        duplicates=sum(count - 1 for count in numbers.values() if count > 1),
        pages_without_truth=matching.pages_without_truth,
        zeros_kept=zeros_kept,
        zeros_total=zeros_total,
        failed_pages=failed_pages,
        timings=timings or [],
    )


def _items(value: Value) -> set[str]:
    if value is None:
        return set()
    return set(value) if isinstance(value, frozenset) else {value}


def _zero_values(value: Value) -> list[str]:
    return sorted(item for item in _items(value) if item.startswith("0"))


def render_markdown(report: Report) -> str:
    """The report, in Hebrew, with no field values."""
    lines = [
        "# תוצאות המדידה",
        "",
        "על הפלט אחרי הכללים ולפני תיקון של אדם. שמות לא נמדדים (SPEC 12).",
        "",
        "| שדה | דיוק | כיסוי | שגיאות שלא סומנו |",
        "|---|---|---|---|",
    ]
    for name, score in report.fields.items():
        if name == "form_type":
            lines.append(
                f"| {FIELD_TITLES[name]} | {score.percent(score.correct, score.total)} | — | — |"
            )
            continue
        lines.append(
            f"| {FIELD_TITLES[name]} | {score.percent(score.correct, score.total)}"
            f" | {score.percent(score.read, score.present)} | {score.unflagged_errors} |"
        )
    unflagged = sum(score.unflagged_errors for score in report.fields.values())
    lines += [
        "",
        f"**שגיאות שלא סומנו, בסך הכול: {unflagged}** (ערך שגוי שלא נשלח לבדיקה).",
        "",
        "| | |",
        "|---|---|",
        f"| רשומות צפויות | {report.expected_records} |",
        f"| רשומות שנוצרו | {report.produced_records} |",
        f"| הותאמו | {report.matched} |",
        f"| חסרות | {len(report.missing)} |",
        f"| עודפות | {len(report.extra)} |",
        f"| כפילויות במספר התחייבות | {report.duplicates} |",
        f"| אפסים מובילים שנשמרו | {_fraction(report.zeros_kept, report.zeros_total)} |",
        f"| עמודים שנכשלו | {report.failed_pages} |",
        f"| עמודים בלי טבלת אמת (לא נמדדו) | {report.pages_without_truth} |",
    ]
    if report.timings:
        per_page = [t.seconds / t.pages for t in report.timings]
        lines.append(
            f"| זמן לעמוד | ממוצע {sum(per_page) / len(per_page):.1f} שניות,"
            f" מקסימום {max(per_page):.1f} |"
        )
    places = {
        FIELD_TITLES[name]: score.places for name, score in report.fields.items() if score.places
    }
    if places or report.missing or report.extra:
        lines += ["", "## איפה לבדוק", ""]
        for title, where in places.items():
            lines.append(f"- {title}, שגיאה שלא סומנה: {', '.join(where)}")
        if report.missing:
            lines.append(f"- רשומות חסרות: {', '.join(report.missing)}")
        if report.extra:
            lines.append(f"- רשומות עודפות: {', '.join(report.extra)}")
    return "\n".join(lines) + "\n"


def _fraction(part: int, whole: int) -> str:
    return f"{part}/{whole}" if whole else "—"
