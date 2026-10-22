"""Gemini provider: one page image in, RawExtraction out; and the name's second read
(read_name: an enlarged crop in, NameReading out), with its own prompt.

Every call counts against the free tier's 20 requests a day, failed ones too, so
retries are few and deliberate:
- the daily quota is used up -> the same page goes to the next key (GEMINI_API_KEYS,
  one per project: the quota is per project), and the used-up key is skipped until
  the quota resets; once every key is used up, QuotaExhausted (the batch stops);
- the key itself is refused (invalid, revoked, API off) -> the next key too, and
  the refused key is skipped for an hour;
- too many requests this minute (429) -> one retry after the delay Gemini asks for,
  if it is short, else the next key;
- 500 / 502 / 503 / 504, or no connection at all -> one retry after a pause;
- anything else (a bad request, a timeout, an answer that doesn't fit the schema,
  any other error from the client) -> ProviderError, no retry.
The client's own retries are off (google-genai's default), so a call is never
repeated behind our back.

One semaphore for the whole server: two uploads at once still make at most
`max_concurrency` calls, which keeps the per-minute limit in reach.

Logs carry the HTTP code and status only: never the error details, the page or
the key. ProviderError messages are fixed Hebrew text for the user.

Owner: A
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx  # comes with google-genai, which raises its transport errors as is
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.rules.senders import sender_names
from app.schemas.extraction import NameReading, RawExtraction

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).with_name("prompts") / "v8.md"
NAME_PROMPT_FILE = Path(__file__).with_name("prompts") / "name_v1.md"
MAX_ATTEMPTS = 2
SERVER_ERROR_WAIT_S = 5.0
MAX_RATE_WAIT_S = 30.0  # if Gemini asks for a longer wait, try the next key instead
_RETRYABLE = {429, 500, 502, 503, 504}
# The daily quota resets at midnight Pacific time (Gemini API rate-limit docs).
QUOTA_RESET_ZONE = ZoneInfo("America/Los_Angeles")
# A refused key may be fixed in Google's console (API turned on, say): ask it again
# after this, rather than only after a restart.
REFUSED_KEY_REST = timedelta(hours=1)

QUOTA_MESSAGE = "המכסה היומית של Gemini נגמרה. אפשר לנסות שוב מחר"
RATE_MESSAGE = "יותר מדי בקשות ל־Gemini בדקה האחרונה. אפשר לנסות שוב בעוד דקה"
UNAVAILABLE_MESSAGE = "שירות Gemini לא זמין כרגע. אפשר לנסות שוב"
TIMEOUT_MESSAGE = "Gemini לא ענה בזמן. אפשר לנסות שוב"
BAD_ANSWER_MESSAGE = "התשובה של Gemini לא הייתה תקינה. אפשר לנסות שוב"
FAILED_MESSAGE = "הפנייה ל־Gemini נכשלה"
# Every key refused: nothing the user can do but tell whoever runs the server.
KEYS_REFUSED_MESSAGE = "Gemini דחה את מפתחות ה־API של השרת. יש לפנות למי שמנהל את השרת"


def load_prompt(path: Path = PROMPT_FILE) -> str:
    """The prompt file without its leading <!-- --> comment, with the sender list in."""
    text = re.sub(r"\A<!--.*?-->\s*", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return text.replace("{senders}", ", ".join(sender_names()))


class GeminiProvider:
    def __init__(
        self,
        clients: Sequence[genai.Client],
        model: str,
        *,
        max_concurrency: int,
        timeout_s: float,
        prompt: str | None = None,
        name_prompt: str | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not clients:
            raise ValueError("GeminiProvider needs at least one client")
        self._clients = list(clients)  # one per key, in the order of GEMINI_API_KEYS
        self._current = 0  # the key in use, shared by every upload on the server
        # Keys skipped until a time, with what they failed with: out of daily quota
        # until it resets, refused for a while. Once every key is out, a page then
        # fails at once instead of spending one request per key.
        self._resting: dict[int, tuple[datetime, _KeyFailure]] = {}
        self._now = now  # tests pass a fake clock
        self._model = model
        self._timeout_s = timeout_s
        self._prompt = prompt if prompt is not None else load_prompt()
        self._name_prompt = (
            name_prompt if name_prompt is not None else load_prompt(NAME_PROMPT_FILE)
        )
        self._sleep = sleep  # tests pass a fake, so a retry doesn't wait for real
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RawExtraction,
            # "low": "medium" was 4x slower with no gain in the spike (PLAN.md).
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            # "high": a handwritten name is small on a whole page, and at the default
            # the model read the crossed-out printed name under it instead.
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            # No tools here: off, so the client neither tries it nor warns on every call.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        # The same settings, answering in the name's schema.
        self._name_config = self._config.model_copy(update={"response_schema": NameReading})

    @property
    def fingerprint(self) -> str:
        """What decides the answer besides the image: CachedProvider's key, so a new
        model, prompt, thinking level, image resolution or schema reads the pages again."""
        return self._fingerprint(self._config, self._prompt, RawExtraction)

    @property
    def name_fingerprint(self) -> str:
        """The same for read_name: its own prompt and schema."""
        return self._fingerprint(self._name_config, self._name_prompt, NameReading)

    def _fingerprint(
        self, config: types.GenerateContentConfig, prompt: str, schema: type[BaseModel]
    ) -> str:
        # Not sort_keys: Gemini writes the answer in the order of the properties, so a
        # new order is a new answer, and the cache must not hand back the old one.
        schema_json = json.dumps(schema.model_json_schema())
        thinking = config.thinking_config.thinking_level
        resolution = config.media_resolution
        return "\n".join((self._model, str(thinking), str(resolution), prompt, schema_json))

    async def extract(self, page: PageImage) -> RawExtraction:
        image = types.Part.from_bytes(data=page.jpeg, mime_type="image/jpeg")
        return await self._ask([image, self._prompt], self._config, RawExtraction)

    async def read_name(self, crop: PageImage) -> NameReading:
        image = types.Part.from_bytes(data=crop.jpeg, mime_type="image/jpeg")
        return await self._ask([image, self._name_prompt], self._name_config, NameReading)

    async def _ask[T: BaseModel](
        self, contents: list, config: types.GenerateContentConfig, schema: type[T]
    ) -> T:
        async with self._semaphore:
            # Every key once, starting from the one in use. The order is fixed here,
            # not read again from _current, which other pages move meanwhile. Wrapping
            # around means a key that ran out yesterday is found again once it's back.
            count = len(self._clients)
            start = self._current
            failures: list[_KeyFailure] = []
            for key in [(start + step) % count for step in range(count)]:
                resting = self._resting.get(key)
                if resting is not None and self._now() < resting[0]:
                    failures.append(resting[1])  # known to fail: don't spend a request on it
                    continue
                try:
                    result = await self._ask_with(self._clients[key], contents, config, schema)
                except _KEY_FAILURES as exc:  # this key only: try the next
                    logger.warning("gemini key %d of %d %s", key + 1, count, _why(exc))
                    failures.append(exc)
                    if (until := _rest_until(exc, self._now())) is not None:
                        self._resting[key] = (until, exc)
                    # So pages starting now skip it; unless another page moved on already.
                    if self._current == key:
                        self._current = (key + 1) % count
                    continue
                self._current = key  # a key that answers: later pages start here
                return result
        if count > 1:
            logger.warning("gemini: none of the %d keys could be used", count)
        raise _no_key_left(failures)

    async def _ask_with[T: BaseModel](
        self,
        client: genai.Client,
        contents: list,
        config: types.GenerateContentConfig,
        schema: type[T],
    ) -> T:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._call(client, contents, config, schema)
            except errors.APIError as exc:
                wait = self._retry_wait(exc, attempt)
                if wait is None:
                    raise _provider_error(exc) from None
                reason = f"{exc.code} {exc.status}"
            except httpx.TransportError as exc:  # no answer at all: refused, reset, DNS
                if attempt == MAX_ATTEMPTS:
                    logger.warning("gemini unreachable: %s", type(exc).__name__)
                    raise ProviderError(UNAVAILABLE_MESSAGE) from None
                wait, reason = SERVER_ERROR_WAIT_S, type(exc).__name__
            except ProviderError:  # from _call: already a message for the user
                raise
            except Exception as exc:  # keep the contract: a provider raises only these two
                logger.error("gemini call failed unexpectedly: %s", type(exc).__name__)
                raise ProviderError(FAILED_MESSAGE) from None
            logger.warning("gemini %s, retrying in %.0fs", reason, wait)
            await self._sleep(wait)
        raise AssertionError("unreachable: the last attempt returns or raises")

    async def _call[T: BaseModel](
        self,
        client: genai.Client,
        contents: list,
        config: types.GenerateContentConfig,
        schema: type[T],
    ) -> T:
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await client.aio.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
        except TimeoutError:
            logger.warning("gemini timed out after %ss", self._timeout_s)
            raise ProviderError(TIMEOUT_MESSAGE) from None
        if not response.text:  # blocked, or no candidate
            logger.warning("gemini returned no text")
            raise ProviderError(BAD_ANSWER_MESSAGE)
        try:
            return schema.model_validate_json(response.text)
        except ValidationError:
            # Not logged: the errors quote the model's text, which holds patient data.
            logger.warning("gemini answer did not fit the schema")
            raise ProviderError(BAD_ANSWER_MESSAGE) from None

    def _retry_wait(self, exc: errors.APIError, attempt: int) -> float | None:
        """Seconds to wait before the next attempt, or None to stop here."""
        if exc.code == 429 and _is_daily_quota(exc):
            return None
        if exc.code not in _RETRYABLE or attempt == MAX_ATTEMPTS:
            return None
        if exc.code == 429:
            wait = _retry_delay(exc)
            return wait if wait is not None and wait <= MAX_RATE_WAIT_S else None
        return SERVER_ERROR_WAIT_S


class _KeyRejected(ProviderError):
    """The key itself was refused (revoked, invalid, API off): another key may work.

    A ProviderError, so if it ever got out of extract() it would still fail just the page.
    """


class _RateLimited(ProviderError):
    """Over this key's per-minute limit, and the wait is too long: another key's
    project has its own limit."""


_KeyFailure = QuotaExhausted | _KeyRejected | _RateLimited
_KEY_FAILURES = (QuotaExhausted, _KeyRejected, _RateLimited)


def _why(failure: _KeyFailure) -> str:
    if isinstance(failure, QuotaExhausted):
        return "is out of daily quota"
    if isinstance(failure, _RateLimited):
        return "is over its per-minute limit"
    return "was refused"


def _rest_until(failure: _KeyFailure, now: datetime) -> datetime | None:
    """Until when not to ask this key again, or None to ask it on the next page."""
    if isinstance(failure, QuotaExhausted):
        return next_quota_reset(now)
    if isinstance(failure, _KeyRejected):
        return now + REFUSED_KEY_REST
    return None  # over its minute: passes before a skip would help


def next_quota_reset(now: datetime) -> datetime:
    """The next midnight in Pacific time, after `now` (timezone-aware)."""
    tomorrow = now.astimezone(QUOTA_RESET_ZONE).date() + timedelta(days=1)
    return datetime.combine(tomorrow, time(), QUOTA_RESET_ZONE)


def _no_key_left(failures: list[_KeyFailure]) -> ProviderError | QuotaExhausted:
    """What the page fails with once every key failed: the soonest to pass wins."""
    if any(isinstance(failure, _RateLimited) for failure in failures):
        return ProviderError(RATE_MESSAGE)  # a minute away: the batch goes on
    if any(isinstance(failure, QuotaExhausted) for failure in failures):
        return QuotaExhausted(QUOTA_MESSAGE)  # no key will do until tomorrow: stop the batch
    return ProviderError(KEYS_REFUSED_MESSAGE)


def _provider_error(exc: errors.APIError) -> ProviderError | QuotaExhausted:
    logger.warning("gemini failed: %s %s", exc.code, exc.status)
    if exc.code == 429 and _is_daily_quota(exc):
        return QuotaExhausted(QUOTA_MESSAGE)
    if _is_bad_key(exc):
        return _KeyRejected(KEYS_REFUSED_MESSAGE)
    if exc.code == 429:
        return _RateLimited(RATE_MESSAGE)
    if exc.code in _RETRYABLE:
        return ProviderError(UNAVAILABLE_MESSAGE)
    return ProviderError(FAILED_MESSAGE)


def _is_daily_quota(exc: errors.APIError) -> bool:
    # The violated quota's id names the period, e.g.
    # "GenerateRequestsPerDayPerProjectPerModel-FreeTier" (seen in the spike).
    return "PerDay" in str(exc.details)


def _is_bad_key(exc: errors.APIError) -> bool:
    # A wrong key is a 400 whose ErrorInfo reason is API_KEY_INVALID; a revoked or
    # leaked key, or a project with the API off, is a 403. Any other 400 is about
    # the page, and would fail on every key.
    return exc.code in (401, 403) or (exc.code == 400 and "API_KEY_INVALID" in str(exc.details))


def _retry_delay(exc: errors.APIError) -> float | None:
    """The RetryInfo delay Gemini sends with a 429, e.g. "37s" or "1.5s"."""
    error = exc.details.get("error", {}) if isinstance(exc.details, dict) else {}
    for detail in error.get("details") or []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and (match := re.fullmatch(r"(\d+(?:\.\d+)?)s", delay)):
            return float(match[1])
    return None
