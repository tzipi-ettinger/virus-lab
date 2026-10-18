# Extraction fixtures (`FakeProvider`)

Real `gemini-3.8-flash` output for sample pages, in the `RawExtraction` shape
(`app/schemas/extraction.py`). Each page gets one fixture, picked from the file name
and the page number: the same page of the same file always gets the same fixture, the
pages of one file cycle through all of them, and different files usually start at
different fixtures (so a multi-file upload doesn't look like duplicates). The two sample
PDFs start at fixtures 3 and 6.

The details are the challenge's modified sample details (ID `11223344`, placeholder
names), not real patients. Model mistakes are kept on purpose, so the rules and the UI
are tested against what the model really returns.

| Fixture | Source | What it exercises |
|---|---|---|
| `01_meuhedet_clean` | part 1 p1, prompt v2 | Clean printed form. ID written as `0011223344` (10 digits) |
| `02_sheba_screenshot_rotated` | part 1 p25, v3 | Needs 90°. Three commitment numbers, handwritten central number and date |
| `03_maccabi_three_centrals` | part 1 p9, v3 | Three central numbers, one record. Commitment as `606/50364186` and `50364186` (same number) |
| `04_wolfson_two_centrals` | part 2 p12, v3 | Two central numbers. Commitment from the vertical sticker |
| `05_kaplan_wrong_date` | part 2 p18, v3 | **Model mistakes:** date `11/8/20` (should be the stamp `20-08-2026`), commitment sticker missed, ID not found |
| `06_rosenblatt_no_commitment` | part 1 p17, v3 | No commitment number (correct). **Model mistake:** year read as `2020` |
| `07_sheba_screenshot_misread` | part 2 p20, v3 | Needs 270°. **Model mistakes:** ID `11223314`, date `25.8` without a year, sender not found |
| `08_provider_error` | — | The call fails: `ProviderError` with a Hebrew message |

`page_rotation_degrees` is the rotation the **unrotated** page needs; `FakeProvider`
subtracts the rotation already applied, so the rotation loop runs as with the real model.
