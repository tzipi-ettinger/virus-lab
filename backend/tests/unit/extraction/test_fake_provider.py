import asyncio
import json

import pytest

from app.extraction.fake_provider import FIXTURES_DIR, FakeProvider
from app.extraction.provider import PageImage, ProviderError
from app.schemas.extraction import RawExtraction

FIXTURES = sorted(FIXTURES_DIR.glob("*.json"))


def page(number: int, rotation: int = 0) -> PageImage:
    return PageImage(
        file_id="f1", filename="forms.pdf", page_number=number, rotation=rotation, jpeg=b""
    )


def extract(provider: FakeProvider, page_image: PageImage) -> RawExtraction:
    return asyncio.run(provider.extract(page_image))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_every_fixture_is_a_raw_extraction_or_an_error(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if "provider_error" in data:
        assert data["provider_error"]
    else:
        RawExtraction.model_validate(data)


def test_page_n_gets_fixture_n():
    provider = FakeProvider()

    result = extract(provider, page(3))

    assert [item.value for item in result.central_numbers] == ["937309", "937310", "937311"]


def test_pages_cycle_through_the_fixtures():
    provider = FakeProvider()

    assert extract(provider, page(1)) == extract(provider, page(1 + len(FIXTURES)))


def test_the_error_fixture_raises_a_hebrew_provider_error():
    provider = FakeProvider()

    with pytest.raises(ProviderError) as error:
        extract(provider, page(8))

    assert "נסי שוב" in error.value.message


@pytest.mark.parametrize(
    ("number", "applied", "needed"),
    [
        (1, 0, 0),  # upright page
        (2, 0, 90),  # rotated page, first look
        (2, 90, 0),  # after the right correction
        (7, 0, 270),
        (7, 180, 90),  # a wrong first guess: still needs more
        (7, 270, 0),
    ],
)
def test_rotation_answer_depends_on_the_rotation_already_applied(number, applied, needed):
    result = extract(FakeProvider(), page(number, rotation=applied))

    assert result.page_rotation_degrees == needed


def test_an_empty_fixtures_dir_fails_loudly(tmp_path):
    with pytest.raises(ValueError):
        FakeProvider(tmp_path)
