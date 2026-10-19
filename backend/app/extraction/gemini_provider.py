"""Gemini provider: one page image in, RawExtraction out.

Every call counts against the free tier's 20 requests a day, failed ones too, so
retries are few and deliberate:
- the daily quota is used up -> the same page goes to the next key (GEMINI_API_KEYS,
  one per project: the quota is per project); once every key is used up,
  QuotaExhausted (the batch stops);
- the key itself is refused (invalid, revoked, API off) -> the next key too;
- too many requests this minute (429) -> one retry after the delay Gemini asks for,
  if it is short; 500 / 502 / 503 / 504, or no connection at all -> one retry after
  a pause;
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
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import httpx  # comes with google-genai, which raises its transport errors as is
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.rules.senders import sender_names
from app.schemas.extraction import RawExtraction

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).with_name("prompts") / "v4.md"
MAX_ATTEMPTS = 2
SERVER_ERROR_WAIT_S = 5.0
MAX_RATE_WAIT_S = 30.0  # if Gemini asks for a longer wait, fail the page instead
_RETRYABLE = {429, 500, 502, 503, 504}

QUOTA_MESSAGE = "המכסה היומית של Gemini נגמרה. אפשר לנסות שוב מחר"
RATE_MESSAGE = "יותר מדי בקשות ל־Gemini בדקה האחרונה. אפשר לנסות שוב בעוד דקה"
UNAVAILABLE_MESSAGE = "שירות Gemini לא זמין כרגע. אפשר לנסות שוב"
TIMEOUT_MESSAGE = "Gemini לא ענה בזמן. אפשר לנסות שוב"
BAD_ANSWER_MESSAGE = "התשובה של Gemini לא הייתה תקינה. אפשר לנסות שוב"
FAILED_MESSAGE = "הפנייה ל־Gemini נכשלה"


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
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not clients:
            raise ValueError("GeminiProvider needs at least one client")
        self._clients = list(clients)  # one per key, in the order of GEMINI_API_KEYS
        self._current = 0  # the key in use, shared by every upload on the server
        self._model = model
        self._timeout_s = timeout_s
        self._prompt = prompt if prompt is not None else load_prompt()
        self._sleep = sleep  # tests pass a fake, so a retry doesn't wait for real
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RawExtraction,
            # "low": "medium" was 4x slower with no gain in the spike (PLAN.md).
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            # No tools here: off, so the client neither tries it nor warns on every call.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    async def extract(self, page: PageImage) -> RawExtraction:
        contents = [types.Part.from_bytes(data=page.jpeg, mime_type="image/jpeg"), self._prompt]
        async with self._semaphore:
            # Every key once, starting from the one in use. The order is fixed here,
            # not read again from _current, which other pages move meanwhile. Wrapping
            # around means a key that ran out yesterday is found again once it's back.
            count = len(self._clients)
            start = self._current
            failures: list[QuotaExhausted | _KeyRejected] = []
            for key in [(start + step) % count for step in range(count)]:
                try:
                    result = await self._extract_with(self._clients[key], contents)
                except (QuotaExhausted, _KeyRejected) as exc:  # this key only: try the next
                    why = (
                        "is out of daily quota"
                        if isinstance(exc, QuotaExhausted)
                        else "was refused"
                    )
                    logger.warning("gemini key %d of %d %s", key + 1, count, why)
                    failures.append(exc)
                    # So pages starting now skip it; unless another page moved on already.
                    if self._current == key:
                        self._current = (key + 1) % count
                    continue
                self._current = key  # a key that answers: later pages start here
                return result
        if count > 1:
            logger.warning("gemini: none of the %d keys could be used", count)
        if any(isinstance(failure, QuotaExhausted) for failure in failures):
            raise QuotaExhausted(QUOTA_MESSAGE)  # stop the batch: no key will do until tomorrow
        raise ProviderError(FAILED_MESSAGE)

    async def _extract_with(self, client: genai.Client, contents: list) -> RawExtraction:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._call(client, contents)
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

    async def _call(self, client: genai.Client, contents: list) -> RawExtraction:
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await client.aio.models.generate_content(
                    model=self._model, contents=contents, config=self._config
                )
        except TimeoutError:
            logger.warning("gemini timed out after %ss", self._timeout_s)
            raise ProviderError(TIMEOUT_MESSAGE) from None
        if not response.text:  # blocked, or no candidate
            logger.warning("gemini returned no text")
            raise ProviderError(BAD_ANSWER_MESSAGE)
        try:
            return RawExtraction.model_validate_json(response.text)
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


def _provider_error(exc: errors.APIError) -> ProviderError | QuotaExhausted:
    logger.warning("gemini failed: %s %s", exc.code, exc.status)
    if exc.code == 429 and _is_daily_quota(exc):
        return QuotaExhausted(QUOTA_MESSAGE)
    if _is_bad_key(exc):
        return _KeyRejected(FAILED_MESSAGE)
    if exc.code == 429:
        return ProviderError(RATE_MESSAGE)
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
