import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
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

    def __init__(self, *script, delay: float = 0.0, gates: list | None = None) -> None:
        """`gates`: one asyncio.Event per call, which the call waits for instead of `delay`."""
        self.script = list(script)
        self.calls: list[dict] = []
        self.delay = delay
        self.gates = gates
        self.in_flight = 0
        self.max_in_flight = 0
        self.aio = self
        self.models = self

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.gates is not None:
                await self.gates[min(len(self.calls), len(self.gates)) - 1].wait()
            else:
                await asyncio.sleep(self.delay)
            step = self.script[min(len(self.calls), len(self.script)) - 1]
            if isinstance(step, BaseException):
                raise step
            return Response(step)
        finally:
            self.in_flight -= 1


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# 10:00 in California (UTC-7 in summer): the daily quota resets in 14 hours.
MORNING = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def provider(clients, sleep=None, **kwargs):
    """One FakeClient, or a list of them: one per key."""
    clients = clients if isinstance(clients, list) else [clients]
    options = {"max_concurrency": 4, "timeout_s": 60, "prompt": "PROMPT", **kwargs}
    return GeminiProvider(clients, "gemini-test", sleep=sleep or Sleeps(), **options)


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
    assert config.media_resolution == types.MediaResolution.MEDIA_RESOLUTION_HIGH
    assert config.automatic_function_calling.disable


def test_the_prompt_lists_every_sender_and_drops_its_comment():
    prompt = load_prompt()

    assert all(name in prompt for name in sender_names())
    assert "{senders}" not in prompt
    assert not prompt.startswith("<!--")
    assert "Owner" not in prompt  # the file's header comment is not sent to the model
    assert "התקבל" in prompt  # v4: the received stamp wins
    assert "2825747366-01" in prompt  # v5: what the first measurement found
    assert "כתב יד רהוט" in prompt  # v7: names in Hebrew cursive
    assert "crossed out" in prompt  # the handwritten name, not the crossed-out one
    assert "best reading of the whole name" not in prompt  # an unclear name is null


def test_a_used_up_daily_quota_stops_at_once():
    client, sleeps = FakeClient(DAILY), Sleeps()

    with pytest.raises(QuotaExhausted) as error:
        run(provider(client, sleeps).extract(PAGE))

    assert error.value.message == gemini_provider.QUOTA_MESSAGE
    assert len(client.calls) == 1  # no retry: it would fail too, and still count
    assert sleeps.waits == []


def test_a_used_up_key_hands_the_page_to_the_next_key():
    first, second, sleeps = FakeClient(DAILY), FakeClient(ANSWER), Sleeps()

    result = run(provider([first, second], sleeps).extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert len(first.calls) == 1 and len(second.calls) == 1
    assert sleeps.waits == []  # another project's quota: no reason to wait


def test_after_a_key_runs_out_the_next_pages_start_from_the_next_key():
    first, second = FakeClient(DAILY), FakeClient(ANSWER)
    shared = provider([first, second])

    run(shared.extract(PAGE))
    run(shared.extract(PAGE))

    assert len(first.calls) == 1  # not asked again for every page
    assert len(second.calls) == 2


def test_every_key_used_up_stops_the_batch():
    clients = [FakeClient(DAILY), FakeClient(DAILY), FakeClient(DAILY)]

    with pytest.raises(QuotaExhausted) as error:
        run(provider(clients).extract(PAGE))

    assert error.value.message == gemini_provider.QUOTA_MESSAGE
    assert [len(client.calls) for client in clients] == [1, 1, 1]


def test_the_keys_wrap_around_so_a_renewed_quota_is_found_again():
    # Both keys run out on one page; after midnight Pacific key 1 has its quota back.
    first, second, clock = FakeClient(DAILY, ANSWER), FakeClient(DAILY), Clock(MORNING)
    shared = provider([first, second], now=clock)

    with pytest.raises(QuotaExhausted):
        run(shared.extract(PAGE))
    clock.now += timedelta(hours=14)
    result = run(shared.extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert len(first.calls) == 2 and len(second.calls) == 1


def test_pages_at_once_each_try_every_key_exactly_once():
    # Seen in review: the loop read the shared key again on each pass. Page A runs
    # through keys 1, 2, 3 and wraps the shared key back to 1 while page B, slow on
    # key 1, is on key 3: B then asked key 1 again and never asked key 2. Now B
    # skips key 2, which A found used up, and asks key 3 once.
    # Each call waits for its gate, so the order is set here and not by timers.

    async def scenario():
        key1 = [asyncio.Event(), asyncio.Event()]  # A's call, then B's
        key2 = [asyncio.Event()]  # A's only: B skips it
        key3 = [asyncio.Event(), asyncio.Event()]  # A's call, then B's
        clients = [FakeClient(DAILY, gates=gates) for gates in (key1, key2, key3)]
        shared = provider(clients)

        async def settle():  # let both pages run up to their next gate
            for _ in range(20):
                await asyncio.sleep(0)

        page_a = asyncio.create_task(shared.extract(PAGE))
        await settle()
        page_b = asyncio.create_task(shared.extract(PAGE))
        await settle()
        for gate in (key1[0], key2[0], key1[1], key3[0], key3[1]):
            gate.set()
            await settle()
        results = await asyncio.gather(page_a, page_b, return_exceptions=True)
        return results, [len(client.calls) for client in clients]

    results, calls = run(scenario())

    assert all(isinstance(result, QuotaExhausted) for result in results)
    assert calls == [2, 1, 2]


def test_the_log_does_not_promise_a_next_key_that_is_not_there(caplog):
    with caplog.at_level(logging.INFO, logger="app.extraction.gemini_provider"):
        with pytest.raises(QuotaExhausted):
            run(provider([FakeClient(DAILY), FakeClient(DAILY)]).extract(PAGE))

    assert "moving" not in caplog.text
    assert "none of the 2 keys could be used" in caplog.text


def test_once_every_key_is_used_up_later_pages_fail_without_asking():
    clients = [FakeClient(DAILY), FakeClient(DAILY)]
    shared = provider(clients, now=Clock(MORNING))

    for _ in range(3):
        with pytest.raises(QuotaExhausted):
            run(shared.extract(PAGE))

    assert [len(client.calls) for client in clients] == [1, 1]


def test_a_used_up_key_is_asked_again_only_after_midnight_pacific():
    used_up, other, clock = FakeClient(DAILY, ANSWER), FakeClient(ANSWER), Clock(MORNING)
    shared = provider([used_up, other], now=clock)
    run(shared.extract(PAGE))  # key 1 runs out, key 2 answers

    other.script = [DAILY]  # key 2 runs out too, a minute before midnight
    clock.now += timedelta(hours=13, minutes=59)
    with pytest.raises(QuotaExhausted):
        run(shared.extract(PAGE))
    assert len(used_up.calls) == 1  # still resting

    clock.now += timedelta(minutes=1)
    assert isinstance(run(shared.extract(PAGE)), RawExtraction)
    assert len(used_up.calls) == 2


@pytest.mark.parametrize(
    "now, reset",
    [
        # 10:00 PDT -> midnight PDT (07:00 UTC)
        (MORNING, datetime(2026, 10, 20, 7, 0, tzinfo=UTC)),
        # 23:30 PST on the day the clocks go back -> midnight PST (08:00 UTC)
        (datetime(2026, 11, 2, 7, 30, tzinfo=UTC), datetime(2026, 11, 2, 8, 0, tzinfo=UTC)),
    ],
)
def test_the_quota_resets_at_the_next_midnight_pacific(now, reset):
    assert gemini_provider.next_quota_reset(now) == reset


REVOKED = api_error(403, "PERMISSION_DENIED")
INVALID_KEY = api_error(
    400,
    "INVALID_ARGUMENT",
    {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"},
)


@pytest.mark.parametrize("refused", [REVOKED, INVALID_KEY], ids=["revoked", "invalid"])
def test_a_refused_key_hands_the_page_to_the_next_key(refused):
    # Seen in review: a bad key failed every page and the server never left it.
    bad, good = FakeClient(refused), FakeClient(ANSWER)
    shared = provider([bad, good])

    run(shared.extract(PAGE))
    run(shared.extract(PAGE))

    assert len(bad.calls) == 1 and len(good.calls) == 2


def test_a_refused_key_is_asked_again_after_an_hour():
    # It may be fixed in Google's console meanwhile, with no restart.
    bad, good, clock = FakeClient(REVOKED, ANSWER), FakeClient(ANSWER), Clock(MORNING)
    shared = provider([bad, good], now=clock)
    run(shared.extract(PAGE))

    def next_page_from_key_1():  # as if another page had just moved back to key 1
        shared._current = 0
        run(shared.extract(PAGE))

    next_page_from_key_1()
    assert len(bad.calls) == 1  # resting: skipped

    clock.now += gemini_provider.REFUSED_KEY_REST
    next_page_from_key_1()
    assert len(bad.calls) == 2


def test_a_bad_request_about_the_page_does_not_try_the_other_keys():
    # Any other 400 is about the page: every key would refuse it, and each try costs.
    first, second = FakeClient(api_error(400, "INVALID_ARGUMENT")), FakeClient(ANSWER)

    with pytest.raises(ProviderError) as error:
        run(provider([first, second]).extract(PAGE))

    assert error.value.message == gemini_provider.FAILED_MESSAGE
    assert second.calls == []


def test_every_key_refused_fails_the_page_but_not_the_batch():
    with pytest.raises(ProviderError) as error:
        run(provider([FakeClient(REVOKED), FakeClient(INVALID_KEY)]).extract(PAGE))

    assert not isinstance(error.value, QuotaExhausted)
    assert type(error.value) is ProviderError  # the private _KeyRejected stays inside
    # Not the general message: with wrong keys on the server, every page says so.
    assert error.value.message == gemini_provider.KEYS_REFUSED_MESSAGE


def test_used_up_and_refused_keys_together_stop_the_batch():
    with pytest.raises(QuotaExhausted):
        run(provider([FakeClient(DAILY), FakeClient(REVOKED)]).extract(PAGE))


def test_a_long_per_minute_wait_hands_the_page_to_the_next_key():
    # Another project has its own per-minute limit: no reason to fail the page.
    first, second, sleeps = FakeClient(per_minute("45s")), FakeClient(ANSWER), Sleeps()

    result = run(provider([first, second], sleeps).extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert sleeps.waits == []


def test_a_key_over_its_minute_and_one_out_for_the_day_fail_the_page_not_the_batch():
    # The per-minute limit passes within a minute, so stopping the whole batch is wrong.
    with pytest.raises(ProviderError) as error:
        run(provider([FakeClient(per_minute("45s")), FakeClient(DAILY)]).extract(PAGE))

    assert error.value.message == gemini_provider.RATE_MESSAGE


def test_a_short_per_minute_wait_still_stays_on_the_key():
    first, second, sleeps = FakeClient(per_minute("7s"), ANSWER), FakeClient(ANSWER), Sleeps()

    run(provider([first, second], sleeps).extract(PAGE))

    assert len(first.calls) == 2 and second.calls == []
    assert sleeps.waits == [7.0]


def test_the_log_names_the_key_by_number_only(caplog):
    first, second = FakeClient(DAILY), FakeClient(ANSWER)

    with caplog.at_level(logging.INFO, logger="app.extraction.gemini_provider"):
        run(provider([first, second]).extract(PAGE))

    assert "key 1 of 2" in caplog.text


def test_a_provider_needs_a_key():
    with pytest.raises(ValueError):
        provider([])


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


def test_no_connection_is_retried_once():
    client, sleeps = FakeClient(httpx.ConnectError("refused"), ANSWER), Sleeps()

    result = run(provider(client, sleeps).extract(PAGE))

    assert isinstance(result, RawExtraction)
    assert sleeps.waits == [gemini_provider.SERVER_ERROR_WAIT_S]


def test_no_connection_twice_fails_the_page_as_a_provider_error():
    # Seen with a real client: without the catch, httpx.ConnectError escaped the
    # provider and the page showed "unexpected error".
    client = FakeClient(httpx.ConnectError("refused"), httpx.ReadError("reset"))

    with pytest.raises(ProviderError) as error:
        run(provider(client).extract(PAGE))

    assert error.value.message == gemini_provider.UNAVAILABLE_MESSAGE
    assert len(client.calls) == 2


def test_any_other_client_error_is_a_provider_error_without_retry():
    client = FakeClient(KeyError("candidates"))

    with pytest.raises(ProviderError) as error:
        run(provider(client).extract(PAGE))

    assert error.value.message == gemini_provider.FAILED_MESSAGE
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "code, status, message",
    [
        (400, "INVALID_ARGUMENT", gemini_provider.FAILED_MESSAGE),
        (403, "PERMISSION_DENIED", gemini_provider.KEYS_REFUSED_MESSAGE),
    ],
)
def test_a_bad_request_or_key_is_not_retried(code, status, message):
    client = FakeClient(api_error(code, status))

    with pytest.raises(ProviderError) as error:
        run(provider(client).extract(PAGE))

    assert error.value.message == message
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


def test_the_fingerprint_changes_with_the_model_or_the_prompt():
    base = provider(FakeClient(ANSWER)).fingerprint

    assert provider(FakeClient(ANSWER)).fingerprint == base  # stable, so the cache hits
    assert provider(FakeClient(ANSWER), prompt="PROMPT v5").fingerprint != base
    other_model = GeminiProvider(
        [FakeClient(ANSWER)], "gemini-other", max_concurrency=1, timeout_s=60, prompt="PROMPT"
    )
    assert other_model.fingerprint != base
