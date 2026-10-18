from pathlib import Path

import pytest

from app.schemas.api import Form

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rules"


@pytest.fixture
def load_form():
    def load(name: str) -> Form:
        return Form.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))

    return load


@pytest.fixture
def fixture_names():
    return sorted(path.stem for path in FIXTURES.glob("*.json"))
