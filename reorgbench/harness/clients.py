"""Model clients behind one small interface, so the harness is provider-neutral.

A client turns (system, messages) into a Completion. Only Anthropic is wired up so far; other providers
plug in by implementing `complete`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..runtime.policy import InfraError


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    stop_reason: str
    model: str
    request_id: str = ""
    latency_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, messages: list[dict[str, str]]) -> Completion: ...


class AnthropicClient:
    """Claude via the official SDK. Thinking stays on (adaptive, the default on current models); effort is
    pinned explicitly because defaults differ by model. Prompt caching is on, so the growing history is
    billed at the cache rate after the first turn."""

    def __init__(self, model: str, *, effort: str | None = "medium", max_tokens: int = 16000):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=4)
        self.model, self.effort, self.max_tokens = model, effort, max_tokens

    def complete(self, system: str, messages: list[dict[str, str]]) -> Completion:
        kwargs: dict[str, Any] = dict(model=self.model, max_tokens=self.max_tokens, system=system, messages=messages,
                                      cache_control={"type": "ephemeral"})
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        t0 = time.monotonic()
        a = self._anthropic
        try:
            r = self.client.messages.create(**kwargs)
        except (a.RateLimitError, a.APIConnectionError, a.InternalServerError) as e:
            # still failing after the SDK's retries: the provider's fault, not the agent's
            raise InfraError(f"{type(e).__name__}: {e}") from e
        except a.APIStatusError as e:
            if e.status_code >= 500 or e.status_code == 529:
                raise InfraError(f"{type(e).__name__}: {e}") from e
            raise
        text = "".join(b.text for b in r.content if b.type == "text")
        u = r.usage
        cached = (getattr(u, "cache_read_input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        return Completion(text, u.input_tokens + cached, u.output_tokens, r.stop_reason or "", r.model,
                          getattr(r, "_request_id", "") or "", time.monotonic() - t0,
                          {"cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                           "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
                           "uncached_in": u.input_tokens})


class FakeClient:
    """For tests: replies come from a function of (system, messages)."""

    def __init__(self, reply: Callable[[str, list[dict[str, str]]], str], model: str = "fake"):
        self.reply, self.model = reply, model
        self.calls = 0

    def complete(self, system: str, messages: list[dict[str, str]]) -> Completion:
        self.calls += 1
        text = self.reply(system, messages)
        return Completion(text, sum(len(m["content"]) for m in messages) // 4 + len(system) // 4,
                          len(text) // 4, "end_turn", self.model)


def make_client(spec: str, **kw: Any) -> LLMClient:
    """'anthropic:claude-haiku-5-5' or a bare Claude model id."""
    provider, _, model = spec.partition(":") if ":" in spec else ("anthropic", "", spec)
    if provider == "anthropic":
        return AnthropicClient(model, **kw)
    raise ValueError(f"no client for provider {provider!r} yet")
