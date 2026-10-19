"""Gemini provider: one page image in, RawExtraction out.

Every call counts against the free tier's 20 requests a day, failed ones too, so
retries are few and deliberate:
- the daily quota is used up -> QuotaExhausted at once, never retried (the batch stops);
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
import json
import logging
import re
from collections.abc import Awaitable, Callable
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
        client: genai.Client,
        model: str,
        *,
        max_concurrency: int,
        timeout_s: float,
        prompt: str | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
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

    @property
    def fingerprint(self) -> str:
        """What decides the answer besides the image: CachedProvider's key, so a new
        model, prompt, thinking level or schema reads the pages again."""
        schema = json.dumps(RawExtraction.model_json_schema(), sort_keys=True)
        thinking = self._config.thinking_config.thinking_level
        return "\n".join((self._model, str(thinking), self._prompt, schema))

    async def extract(self, page: PageImage) -> RawExtraction:
        contents = [types.Part.from_bytes(data=page.jpeg, mime_type="image/jpeg"), self._prompt]
        async with self._semaphore:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    return await self._call(contents)
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

    async def _call(self, contents: list) -> RawExtraction:
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self._client.aio.models.generate_content(
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


def _provider_error(exc: errors.APIError) -> ProviderError | QuotaExhausted:
    logger.warning("gemini failed: %s %s", exc.code, exc.status)
    if exc.code == 429 and _is_daily_quota(exc):
        return QuotaExhausted(QUOTA_MESSAGE)
    if exc.code == 429:
        return ProviderError(RATE_MESSAGE)
    if exc.code in _RETRYABLE:
        return ProviderError(UNAVAILABLE_MESSAGE)
    return ProviderError(FAILED_MESSAGE)


def _is_daily_quota(exc: errors.APIError) -> bool:
    # The violated quota's id names the period, e.g.
    # "GenerateRequestsPerDayPerProjectPerModel-FreeTier" (seen in the spike).
    return "PerDay" in str(exc.details)


def _retry_delay(exc: errors.APIError) -> float | None:
    """The RetryInfo delay Gemini sends with a 429, e.g. "37s" or "1.5s"."""
    error = exc.details.get("error", {}) if isinstance(exc.details, dict) else {}
    for detail in error.get("details") or []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and (match := re.fullmatch(r"(\d+(?:\.\d+)?)s", delay)):
            return float(match[1])
    return None
