import asyncio
import json
import traceback

import pytest

from app.extraction.fake_provider import FIXTURES_DIR, FakeProvider
from app.extraction.provider import PageImage, ProviderError
from app.schemas.extraction import RawExtraction

FIXTURES = sorted(FIXTURES_DIR.glob("*.json"))
ERROR_FIXTURE = FIXTURES.index(FIXTURES_DIR / "08_provider_error.json")


def page(number: int, rotation: int = 0, filename: str = "forms.pdf") -> PageImage:
    return PageImage(
        file_id="f1", filename=filename, page_number=number, rotation=rotation, jpeg=b""
    )


def extract(provider: FakeProvider, page_image: PageImage) -> RawExtraction:
    return asyncio.run(provider.extract(page_image))


def page_for(provider: FakeProvider, fixture: int, rotation: int = 0) -> PageImage:
    """The page of forms.pdf that gets fixture number `fixture` (0-based)."""
    for number in range(1, len(FIXTURES) + 1):
        candidate = page(number, rotation)
        if provider.fixture_index(candidate) == fixture:
            return candidate
    raise AssertionError("every fixture is reachable within one cycle")


def fixture_data(fixture: int) -> dict:
    return json.loads(FIXTURES[fixture].read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_every_fixture_is_a_raw_extraction_or_an_error(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if "provider_error" in data:
        assert data["provider_error"]
    else:
        RawExtraction.model_validate(data)


def test_a_page_gets_its_fixture():
    provider = FakeProvider()
    maccabi = FIXTURES.index(FIXTURES_DIR / "03_maccabi_three_centrals.json")

    result = extract(provider, page_for(provider, maccabi))

    assert [item.value for item in result.central_numbers] == ["937309", "937310", "937311"]


def test_one_file_cycles_through_every_fixture():
    provider = FakeProvider()

    used = {provider.fixture_index(page(number)) for number in range(1, len(FIXTURES) + 1)}

    assert used == set(range(len(FIXTURES)))


def test_the_same_page_always_gets_the_same_result():
    assert extract(FakeProvider(), page(1)) == extract(FakeProvider(), page(1))


def test_two_files_start_at_different_fixtures():
    # Otherwise every multi-file upload would look like duplicates (DUPLICATE_RECORD).
    provider = FakeProvider()

    first_pages = {provider.fixture_index(page(1, filename=f"scan_{i}.pdf")) for i in range(5)}

    assert len(first_pages) > 1


def test_a_result_is_a_private_copy():
    provider = FakeProvider()
    target = page_for(provider, 0)
    first = extract(provider, target)
    first.national_id.value = "changed"
    first.central_numbers.clear()

    again = extract(provider, target)

    assert again.national_id.value == fixture_data(0)["national_id"]["value"]
    assert len(again.central_numbers) == len(fixture_data(0)["central_numbers"])


def test_the_error_fixture_raises_a_hebrew_provider_error():
    provider = FakeProvider()

    with pytest.raises(ProviderError) as error:
        extract(provider, page_for(provider, ERROR_FIXTURE))

    assert "נסי שוב" in error.value.message


def test_each_failure_is_a_new_error():
    provider = FakeProvider()
    target = page_for(provider, ERROR_FIXTURE)
    errors = []
    for _ in range(3):
        with pytest.raises(ProviderError) as error:
            extract(provider, target)
        errors.append(error.value)

    assert len({id(e) for e in errors}) == 3
    depths = {len(traceback.extract_tb(e.__traceback__)) for e in errors}
    assert len(depths) == 1  # the traceback doesn't grow


@pytest.mark.parametrize(
    ("fixture_name", "applied", "needed"),
    [
        ("01_meuhedet_clean", 0, 0),  # upright page
        ("02_sheba_screenshot_rotated", 0, 90),  # rotated page, first look
        ("02_sheba_screenshot_rotated", 90, 0),  # after the right correction
        ("07_sheba_screenshot_misread", 0, 270),
        ("07_sheba_screenshot_misread", 180, 90),  # a wrong first guess: still needs more
        ("07_sheba_screenshot_misread", 270, 0),
    ],
)
def test_rotation_answer_depends_on_the_rotation_already_applied(fixture_name, applied, needed):
    provider = FakeProvider()
    fixture = FIXTURES.index(FIXTURES_DIR / f"{fixture_name}.json")

    result = extract(provider, page_for(provider, fixture, rotation=applied))

    assert result.page_rotation_degrees == needed


def test_an_empty_fixtures_dir_fails_loudly(tmp_path):
    with pytest.raises(ValueError):
        FakeProvider(tmp_path)
