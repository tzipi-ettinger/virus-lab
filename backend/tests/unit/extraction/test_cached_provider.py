import asyncio
import logging

import pytest

from app.extraction.cached_provider import CachedProvider
from app.extraction.fake_provider import FIXTURES_DIR
from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.schemas.extraction import RawExtraction

READING = RawExtraction.model_validate_json(
    (FIXTURES_DIR / "03_maccabi_three_centrals.json").read_text(encoding="utf-8")
)
PAGE = PageImage("f1", "forms.pdf", 1, 0, b"\xff\xd8 page one")


class Script:
    """Answers from a list: a reading, or an exception to raise. Counts the calls."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers) or [READING]
        self.calls = 0

    async def extract(self, page: PageImage) -> RawExtraction:
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        if isinstance(answer, BaseException):
            raise answer
        return answer.model_copy(deep=True)


def run(coro):
    return asyncio.run(coro)


def test_a_page_read_once_is_answered_from_the_cache(tmp_path):
    inner = Script()
    cache = CachedProvider(inner, "model+prompt", tmp_path)

    first = run(cache.extract(PAGE))
    second = run(cache.extract(PAGE))

    assert inner.calls == 1  # the second one cost no quota
    assert first == second == READING
    assert (cache.hits, cache.misses) == (1, 1)


def test_the_same_page_under_another_name_is_a_hit(tmp_path):
    inner = Script()
    cache = CachedProvider(inner, "fp", tmp_path)

    run(cache.extract(PAGE))
    run(cache.extract(PageImage("f9", "renamed.pdf", 7, 0, PAGE.jpeg)))

    assert inner.calls == 1


def test_another_image_is_a_miss(tmp_path):
    # A page turned another way is another image: it is read, not taken from the cache.
    inner = Script()
    cache = CachedProvider(inner, "fp", tmp_path)

    run(cache.extract(PAGE))
    run(cache.extract(PageImage("f1", "forms.pdf", 1, 90, b"\xff\xd8 page one, turned")))

    assert inner.calls == 2


def test_a_new_prompt_or_model_reads_the_pages_again(tmp_path):
    inner = Script()

    run(CachedProvider(inner, "model\nprompt v4", tmp_path).extract(PAGE))
    run(CachedProvider(inner, "model\nprompt v5", tmp_path).extract(PAGE))

    assert inner.calls == 2


def test_an_error_is_not_cached(tmp_path):
    inner = Script(ProviderError("המודל לא ענה"), READING)
    cache = CachedProvider(inner, "fp", tmp_path)

    with pytest.raises(ProviderError):
        run(cache.extract(PAGE))
    assert run(cache.extract(PAGE)) == READING  # tried again, not a cached failure

    assert inner.calls == 2
    assert list(tmp_path.glob("*.json")) != []


def test_a_used_up_quota_passes_through(tmp_path):
    cache = CachedProvider(Script(QuotaExhausted("המכסה נגמרה")), "fp", tmp_path)

    with pytest.raises(QuotaExhausted):
        run(cache.extract(PAGE))

    assert list(tmp_path.iterdir()) == []


def test_a_broken_entry_is_read_again_and_replaced(tmp_path):
    inner = Script()
    cache = CachedProvider(inner, "fp", tmp_path)
    run(cache.extract(PAGE))
    [entry] = tmp_path.glob("*.json")
    entry.write_text('{"first_name": "half a fi', encoding="utf-8")

    assert run(cache.extract(PAGE)) == READING

    assert inner.calls == 2
    assert RawExtraction.model_validate_json(entry.read_bytes()) == READING


def test_a_cache_that_cant_be_written_never_fails_the_page(tmp_path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("a file where the cache dir should be")
    cache = CachedProvider(Script(), "fp", blocked)

    assert run(cache.extract(PAGE)) == READING


def test_logs_carry_no_reading(tmp_path, caplog):
    cache = CachedProvider(Script(), "fp", tmp_path)

    with caplog.at_level(logging.INFO, logger="app.extraction.cached_provider"):
        run(cache.extract(PAGE))
        run(cache.extract(PAGE))

    assert "cache hit" in caplog.text
    assert READING.national_id.value not in caplog.text
    assert "forms.pdf" not in caplog.text
