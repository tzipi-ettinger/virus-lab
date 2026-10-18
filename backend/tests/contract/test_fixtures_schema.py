"""Every rules fixture parses as the Form in schemas/api.py (assemble.py output, SPEC 9.6).

Owner: shared
"""

import json
from pathlib import Path

import pytest

from app.schemas.api import Form

RULES_FIXTURES = sorted((Path(__file__).parents[1] / "fixtures" / "rules").glob("*.json"))


@pytest.mark.parametrize("path", RULES_FIXTURES, ids=lambda p: p.name)
def test_rules_fixture_is_a_form(path):
    Form.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_rules_fixtures_exist():
    assert len(RULES_FIXTURES) == 4
