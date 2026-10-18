## What and why

<!-- 1–3 lines: what changed and why. Link the PLAN or SPEC section if there is one. -->

## How I tested

<!-- Tests, manual run, screenshot for a UI change. -->

## Checklist

- [ ] Touches only my own files, or this is a shared PR that both of us approve (see `.github/CODEOWNERS`)
- [ ] Changed `schemas/api.py`? Ran `python -m scripts.export_openapi` in `backend/` and `npm run gen:api` in `frontend/`, and the commit includes the generated files
- [ ] No real patient documents, and no names or national IDs in logs, fixtures or screenshots
- [ ] No API key or `.env` in the diff
- [ ] If a decision was made or the schedule moved, I updated `PLAN.md`
