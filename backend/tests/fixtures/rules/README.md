# Rules fixtures

Input to `apply_rules(form)`: a form as `assemble.py` returns it (SPEC v0.2 section 9.6), with `raw`, `model_status` and `evidence` only. `value` is `null`, there are no `issues` yet, and every flag is `false`. The values are made up.

| File | What it covers |
|---|---|
| `clean.json` | Printed form, every field read. The 8-digit ID gets padded to 9 digits (`ID_PADDED`, info) |
| `multi_values.json` | 3 central numbers (one is a duplicate, `DUPLICATE_REMOVED`), 2 commitments (one with the lab prefix `606/`, dropped as `COMMITMENT_PREFIX_REMOVED`, info), rotated page |
| `unclear.json` | Names and date `unclear`, a 10-digit ID with a leading 0 (`ID_NORMALIZED`), unknown sender, 5-digit central number |
| `no_commitment.json` | No commitment number on the page (`REQUIRED_MISSING`). It becomes one record, and approval stays blocked until the user fills it in |
