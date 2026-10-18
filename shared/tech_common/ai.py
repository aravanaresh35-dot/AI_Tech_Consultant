"""Central AI client wrapper.

Mode rules (kept deliberately simple and honest):
  * DEMO_MODE=true            -> always "demo" (no model is ever called).
  * DEMO_MODE=false           -> "live"; fails loudly if key/model are missing.
  * DEMO_MODE=auto (default)  -> "live" only if ANTHROPIC_API_KEY and ANTHROPIC_MODEL are set.

The model name is NEVER hard-coded: set ANTHROPIC_MODEL to an identifier you have
verified is available to your account. Callers must check `ai.is_live` and use a
deterministic, clearly labelled path when it is False.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .logging_setup import log

logger = logging.getLogger("ai")
T = TypeVar("T", bound=BaseModel)


class AIUnavailable(RuntimeError):
    """Live mode was requested but cannot be used (missing key/model, API failure)."""


@dataclass
class AIResult:
    text: str
    mode: str  # always "live" for results produced by this class
    model: str
    prompt_version: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_ms: float
    cost_usd: Optional[float]  # None unless pricing env vars are configured


@dataclass
class UsageLog:
    calls: list[dict] = field(default_factory=list)

    def add(self, r: AIResult) -> None:
        self.calls.append(
            {
                "model": r.model,
                "prompt_version": r.prompt_version,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "latency_ms": round(r.latency_ms, 1),
                "cost_usd": r.cost_usd,
            }
        )
        self.calls = self.calls[-500:]

    def summary(self) -> dict:
        n = len(self.calls)
        ins = [c["input_tokens"] for c in self.calls if c["input_tokens"] is not None]
        outs = [c["output_tokens"] for c in self.calls if c["output_tokens"] is not None]
        costs = [c["cost_usd"] for c in self.calls if c["cost_usd"] is not None]
        return {
            "live_calls": n,
            "input_tokens": sum(ins) if ins else None,
            "output_tokens": sum(outs) if outs else None,
            "estimated_cost_usd": round(sum(costs), 6) if costs else None,
            "avg_latency_ms": round(sum(c["latency_ms"] for c in self.calls) / n, 1) if n else None,
        }


def _float_env(name: str) -> Optional[float]:
    v = os.environ.get(name)
    try:
        return float(v) if v else None
    except ValueError:
        return None


class AIClient:
    def __init__(self, model_env: str = "ANTHROPIC_MODEL", key_env: str = "ANTHROPIC_API_KEY"):
        self.model = os.environ.get(model_env, "").strip()
        self._key = os.environ.get(key_env, "").strip()
        flag = os.environ.get("DEMO_MODE", "auto").strip().lower()
        self.timeout = float(os.environ.get("AI_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.environ.get("AI_MAX_RETRIES", "2"))
        self.price_in = _float_env("MODEL_PRICE_INPUT_PER_MTOK")
        self.price_out = _float_env("MODEL_PRICE_OUTPUT_PER_MTOK")
        self.usage = UsageLog()
        self._client: Any = None
        if flag in ("true", "1", "yes"):
            self.mode = "demo"
        elif flag in ("false", "0", "no"):
            self.mode = "live"
        else:
            self.mode = "live" if (self._key and self.model) else "demo"

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "model": (self.model or None) if self.is_live else None,
            "usage": self.usage.summary(),
        }

    def _sdk(self):
        if self._client is None:
            if not (self._key and self.model):
                raise AIUnavailable("Live mode needs ANTHROPIC_API_KEY and ANTHROPIC_MODEL.")
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=self._key, timeout=self.timeout, max_retries=self.max_retries
            )
        return self._client

    def _cost(self, i: Optional[int], o: Optional[int]) -> Optional[float]:
        if i is None or o is None or self.price_in is None or self.price_out is None:
            return None
        return (i * self.price_in + o * self.price_out) / 1_000_000

    def generate(self, system: str, user: Any, prompt_version: str, max_tokens: int = 1500) -> AIResult:
        """Call Claude. `user` may be a string or a list of content blocks (e.g. images)."""
        if not self.is_live:
            raise AIUnavailable("generate() called in demo mode; callers must use the demo path.")
        sdk = self._sdk()
        content = user if isinstance(user, list) else [{"type": "text", "text": user}]
        start = time.perf_counter()
        try:
            resp = sdk.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
        except Exception as exc:  # SDK already retried transient errors
            raise AIUnavailable(f"Model call failed: {type(exc).__name__}") from exc
        latency = (time.perf_counter() - start) * 1000
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        i = getattr(resp.usage, "input_tokens", None)
        o = getattr(resp.usage, "output_tokens", None)
        result = AIResult(text, "live", self.model, prompt_version, i, o, latency, self._cost(i, o))
        self.usage.add(result)
        log(logger, "ai_call", model=self.model, prompt_version=prompt_version,
            input_tokens=i, output_tokens=o, latency_ms=round(latency, 1))
        return result

    def generate_json(self, system: str, user: str, schema: Type[T], prompt_version: str,
                      max_tokens: int = 2500) -> tuple[T, AIResult]:
        """Ask for JSON, validate with pydantic, retry once with the validation error."""
        sys_p = system + "\n\nRespond with ONE JSON object only. No prose, no markdown fences."
        prompt = user
        last_err = ""
        for _ in range(2):
            res = self.generate(sys_p, prompt, prompt_version, max_tokens)
            try:
                data = json.loads(extract_json(res.text))
                return schema.model_validate(data), res
            except (json.JSONDecodeError, ValidationError) as exc:
                last_err = str(exc)[:500]
                prompt = f"{user}\n\nYour previous reply was invalid ({last_err}). Return corrected JSON only."
        raise AIUnavailable(f"Model did not return valid structured output: {last_err}")


def extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text
