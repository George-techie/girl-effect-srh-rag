"""OpenRouter client.

A single API key reaches GPT, Gemini and Claude — the three model families Girl
Effect runs in production — which lets the benchmark compare them on identical
prompts and identical retrieved context.

The client records latency and token usage for every call so that the
cost/latency columns of the evaluation report come from measurement rather than
estimation.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from src import config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class MissingAPIKey(RuntimeError):
    """Raised with a pointer to setup instructions rather than a bare KeyError."""


@dataclass
class LLMResponse:
    """One completion, plus the accounting we need for the evaluation report."""

    text: str
    model: str
    role: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1
    finish_reason: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class CallLog:
    """In-process ledger of every LLM call, for per-node cost and latency stats."""

    calls: list[LLMResponse] = field(default_factory=list)

    def record(self, response: LLMResponse) -> None:
        self.calls.append(response)

    def reset(self) -> None:
        self.calls.clear()

    def summary(self) -> dict[str, Any]:
        by_role: dict[str, dict[str, int]] = {}
        for call in self.calls:
            bucket = by_role.setdefault(
                call.role,
                {"calls": 0, "latency_ms": 0, "prompt_tokens": 0, "completion_tokens": 0},
            )
            bucket["calls"] += 1
            bucket["latency_ms"] += call.latency_ms
            bucket["prompt_tokens"] += call.prompt_tokens
            bucket["completion_tokens"] += call.completion_tokens
        return {
            "total_calls": len(self.calls),
            "total_latency_ms": sum(c.latency_ms for c in self.calls),
            "total_tokens": sum(c.total_tokens for c in self.calls),
            "by_role": by_role,
        }


#: Module-level ledger. Reset it at the start of each benchmark case.
call_log = CallLog()


class LLMClient:
    """Thin wrapper over the OpenAI SDK pointed at OpenRouter."""

    def __init__(self, api_key: str | None = None, timeout: float = 90.0) -> None:
        key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise MissingAPIKey(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add "
                "a key from https://openrouter.ai/keys"
            )
        self._client = OpenAI(
            api_key=key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
            default_headers={
                # Optional attribution shown on the OpenRouter dashboard.
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:8501"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "girl-effect-poc"),
            },
        )

    # -- core ---------------------------------------------------------------

    def complete(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Run a chat completion for a named node role.

        `role` selects the model from ``config.MODELS`` and is also the key the
        call is logged under, so per-node cost and latency fall out for free.
        """
        resolved = model or config.MODELS.get(role)
        if resolved is None:
            raise KeyError(
                f"No model registered for role {role!r}. "
                f"Known roles: {sorted(config.MODELS)}"
            )

        kwargs: dict[str, Any] = {
            "model": resolved,
            "messages": messages,
            "temperature": (
                config.CLASSIFIER_TEMPERATURE if temperature is None else temperature
            ),
            "max_tokens": max_tokens or config.GENERATION_MAX_TOKENS,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                completion = self._client.chat.completions.create(**kwargs)
                break
            except (RateLimitError, APITimeoutError) as exc:
                # Transient: back off and retry.
                last_error = exc
                if attempt == max_retries:
                    raise
                time.sleep(min(2**attempt, 8))
            except APIError as exc:
                # Some providers reject response_format; retry once without it
                # rather than losing the call, then parse the JSON leniently.
                last_error = exc
                if json_mode and "response_format" in kwargs and attempt < max_retries:
                    kwargs.pop("response_format")
                    continue
                raise
        else:  # pragma: no cover - loop always breaks or raises
            raise RuntimeError(f"LLM call failed for role {role!r}") from last_error

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = completion.choices[0]
        usage = completion.usage

        # Reasoning models sometimes return an empty `content` and put the whole
        # answer in a reasoning field. Falling back keeps such models usable
        # rather than silently yielding blank responses.
        text = (choice.message.content or "").strip()
        if not text:
            for attr in ("reasoning", "reasoning_content"):
                fallback_text = getattr(choice.message, attr, None)
                if fallback_text:
                    text = str(fallback_text).strip()
                    break

        response = LLMResponse(
            text=text,
            model=resolved,
            role=role,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            attempts=attempt,
            finish_reason=getattr(choice, "finish_reason", None),
        )
        call_log.record(response)
        return response

    def stream(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Yield text deltas as they arrive. Returns the `LLMResponse` at the end.

        A generator with a return value, so a caller can do::

            text = yield from client.stream(...)      # inside a generator
            # or
            gen = client.stream(...); ... ; response = gen.value   # via _Streamed

        No retry loop. `complete` can retry because nothing has been shown yet;
        once the first token has reached her screen a retry would rewrite what
        she is already reading, so a stream that fails must fail visibly and let
        the caller fall back.
        """
        resolved = model or config.MODELS.get(role)
        if resolved is None:
            raise KeyError(f"No model registered for role {role!r}")

        started = time.perf_counter()
        chunks: list[str] = []
        finish_reason = None

        completion = self._client.chat.completions.create(
            model=resolved,
            messages=messages,
            temperature=(config.CLASSIFIER_TEMPERATURE
                         if temperature is None else temperature),
            max_tokens=max_tokens or config.GENERATION_MAX_TOKENS,
            stream=True,
        )

        for event in completion:
            if not event.choices:
                continue
            choice = event.choices[0]
            piece = getattr(choice.delta, "content", None)
            if piece:
                chunks.append(piece)
                yield piece
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason

        response = LLMResponse(
            text="".join(chunks).strip(),
            model=resolved,
            role=role,
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=finish_reason,
        )
        call_log.record(response)
        return response

    def complete_json(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        fallback: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], LLMResponse]:
        """Chat completion parsed as JSON.

        **The provider's structured-output mode is not used by default**, and
        that is a deliberate reversal. Measured on the triage classifier:

            plain call          -> {"domains": ["consent_relationships"],
                                    "confidence": 0.96, ...}   correct
            response_format set -> {"domains": [], "confidence": 0.0,
                                    "clarification_needed": true,
                                    "reasoning": "too vague"}  wrong

        Same model, same prompt, same message. Constrained decoding consumed a
        small model's capacity: it satisfied the format and failed the task. The
        failure was invisible because the output was still *valid JSON* — a
        schema check passes, and only a semantic check catches it.

        The prompts already demand JSON and `extract_json` is deliberately
        forgiving, so the format constraint bought nothing and cost accuracy.
        It is retried *only* when lenient parsing genuinely fails, which is the
        case it was meant for.

        A `fallback` of ``None`` means malformed JSON raises; supplying one lets
        safety-critical nodes fail closed instead of crashing the graph.
        """
        response = self.complete(
            role,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
        )
        try:
            return extract_json(response.text), response
        except ValueError:
            pass

        # Lenient parsing failed. Now the format constraint is worth its cost.
        try:
            retry = self.complete(
                role,
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
            )
            return extract_json(retry.text), retry
        except (ValueError, APIError) as exc:
            if fallback is None:
                raise ValueError(
                    f"could not parse JSON for role {role!r} with or without "
                    f"structured-output mode"
                ) from exc
            return dict(fallback), response


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object out of a model response.

    Handles the three things models actually do: clean JSON, JSON fenced in
    markdown, and JSON with prose wrapped around it.
    """
    text = text.strip()
    if not text:
        raise ValueError("empty response")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Last resort: the outermost braces in the response.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"could not parse JSON from response: {text[:200]!r}")


_client: LLMClient | None = None


def get_client() -> LLMClient:
    """Process-wide client, created on first use so imports stay key-free."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
