import asyncio
import logging

import pytest
from google.genai import errors, types

from app.extraction import gemini_provider
from app.extraction.fake_provider import FIXTURES_DIR
from app.extraction.gemini_provider import GeminiProvider, load_prompt
from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.rules.senders import sender_names
from app.schemas.extraction import RawExtraction

ANSWER = (FIXTURES_DIR / "03_maccabi_three_centrals.json").read_text(encoding="utf-8")
PAGE = PageImage("f1", "forms.pdf", 1, 0, b"\xff\xd8 jpeg bytes")


def api_error(code: int, status: str, *details: dict) -> errors.APIError:
    """Shaped like Gemini's errors: {"error": {"code", "status", "message", "details"}}."""
    body = {"error": {"code": code, "status": status, "message": "x", "details": list(details)}}
    return (errors.ClientError if code < 500 else errors.ServerError)(code, body)


DAILY = api_error(
    429,
    "RESOURCE_EXHAUSTED",
    {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
    },
)


def per_minute(delay: str) -> errors.APIError:
    return api_error(
        429,
        "RESOURCE_EXHAUSTED",
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}],
        },
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
    )


class Response:
    def __init__(self, text):
        self.text = text


class FakeClient:
    """client.aio.models.generate_content, answering from a script: text or an exception."""

    def __init__(self, *script, delay: float = 0.0) -> None:
        self.script = list(script)
        self.calls: list[dict] = []
        self.delay = delay
        self.in_flight = 0
        self.max_in_flight = 0
        self.aio = self
        self.models = self

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            step = self.script[min(len(self.calls), len(self.script)) - 1]
            if isinstance(step, BaseException):
                raise step
            return Response(step)
        finally:
            self.in_flight -= 1


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def provider(client, sleep=None, **kwargs):
    options = {"max_concurrency": 4, "timeout_s": 60, "prompt": "PROMPT", **kwargs}
    return GeminiProvider(client, "gemini-test", sleep=sleep or Sleeps(), **options)


def run(coro):
    return asyncio.run(coro)


def test_a_page_comes_back_as_raw_extraction():
    client = FakeClient(ANSWER)

    result = run(provider(client).extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert [item.value for item in result.central_numbers] == ["937309", "937310", "937311"]
    [call] = client.calls
    assert call["model"] == "gemini-test"
    image, prompt = call["contents"]
    assert image.inline_data.data == PAGE.jpeg
    assert image.inline_data.mime_type == "image/jpeg"
    assert prompt == "PROMPT"
    config: types.GenerateContentConfig = call["config"]
    assert config.response_schema is RawExtraction
    assert config.response_mime_type == "application/json"
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


def test_the_prompt_lists_every_sender_and_drops_its_comment():
    prompt = load_prompt()

    assert all(name in prompt for name in sender_names())
    assert "{senders}" not in prompt
    assert not prompt.startswith("<!--")
    assert "Owner" not in prompt  # the file's header comment is not sent to the model
    assert "התקבל" in prompt  # v4: the received stamp wins


def test_a_used_up_daily_quota_stops_at_once():
    client, sleeps = FakeClient(DAILY), Sleeps()

    with pytest.raises(QuotaExhausted) as error:
        run(provider(client, sleeps).extract(PAGE))

    assert error.value.message == gemini_provider.QUOTA_MESSAGE
    assert len(client.calls) == 1  # no retry: it would fail too, and still count
    assert sleeps.waits == []


def test_the_per_minute_limit_is_retried_once_after_the_asked_delay():
    client, sleeps = FakeClient(per_minute("7s"), ANSWER), Sleeps()

    result = run(provider(client, sleeps).extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert len(client.calls) == 2
    assert sleeps.waits == [7.0]


def test_a_long_per_minute_delay_fails_the_page_instead_of_waiting():
    client, sleeps = FakeClient(per_minute("45s"), ANSWER), Sleeps()

    with pytest.raises(ProviderError) as error:
        run(provider(client, sleeps).extract(PAGE))

    assert error.value.message == gemini_provider.RATE_MESSAGE
    assert len(client.calls) == 1


@pytest.mark.parametrize("code", [500, 503])
def test_a_server_error_is_retried_once(code):
    client, sleeps = FakeClient(api_error(code, "UNAVAILABLE"), ANSWER), Sleeps()

    result = run(provider(client, sleeps).extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert sleeps.waits == [gemini_provider.SERVER_ERROR_WAIT_S]


def test_two_server_errors_fail_the_page():
    client = FakeClient(api_error(503, "UNAVAILABLE"), api_error(503, "UNAVAILABLE"))

    with pytest.raises(ProviderError) as error:
        run(provider(client).extract(PAGE))

    assert error.value.message == gemini_provider.UNAVAILABLE_MESSAGE
    assert len(client.calls) == gemini_provider.MAX_ATTEMPTS


@pytest.mark.parametrize("code, status", [(400, "INVALID_ARGUMENT"), (403, "PERMISSION_DENIED")])
def test_a_bad_request_or_key_is_not_retried(code, status):
    client = FakeClient(api_error(code, status))

    with pytest.raises(ProviderError) as error:
        run(provider(client).extract(PAGE))

    assert error.value.message == gemini_provider.FAILED_MESSAGE
    assert len(client.calls) == 1


def test_a_slow_answer_times_out_without_a_retry():
    client = FakeClient(ANSWER, delay=1.0)

    with pytest.raises(ProviderError) as error:
        run(provider(client, timeout_s=0.05).extract(PAGE))

    assert error.value.message == gemini_provider.TIMEOUT_MESSAGE
    assert len(client.calls) == 1


@pytest.mark.parametrize("text", [None, "", "not json", '{"page_rotation_degrees": 0}'])
def test_an_answer_that_does_not_fit_the_schema_fails_the_page(text):
    with pytest.raises(ProviderError) as error:
        run(provider(FakeClient(text)).extract(PAGE))

    assert error.value.message == gemini_provider.BAD_ANSWER_MESSAGE


def test_calls_are_limited_across_uploads():
    # One provider serves the whole server: its limit holds for everyone.
    client = FakeClient(ANSWER, delay=0.02)
    shared = provider(client, max_concurrency=2)

    async def two_uploads():
        await asyncio.gather(*(shared.extract(PAGE) for _ in range(6)))

    run(two_uploads())

    assert client.max_in_flight == 2


def test_logs_carry_the_code_but_not_the_details_or_the_answer(caplog):
    secret = "ישראל ישראלי 001122334"
    leaky = api_error(400, "INVALID_ARGUMENT", {"reason": secret})
    bad_answer = '{"first_name": "' + secret + '"}'

    with caplog.at_level(logging.INFO, logger="app.extraction.gemini_provider"):
        for script in (leaky, bad_answer):
            with pytest.raises(ProviderError):
                run(provider(FakeClient(script)).extract(PAGE))

    assert "400" in caplog.text
    assert secret not in caplog.text
