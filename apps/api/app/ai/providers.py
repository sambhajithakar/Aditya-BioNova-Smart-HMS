"""AI providers.

* ``MockProvider`` — in-process and deterministic; never leaves the server, so
  it may receive any data class. Each task registers a handler.
* ``OpenAICompatibleProvider`` — POST ``{base}/v1/chat/completions`` (vLLM,
  Ollama, llama.cpp server or a commercial endpoint). Its data ceiling and
  region are DECLARED in settings; it is only called when AI_LIVE_ENABLED is
  true and a base URL is configured. Transport is injectable for tests.
"""
from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from ..config import Settings
from .gateway import AIRequest, AIResult, DataClass

HttpPost = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]
MockHandler = Callable[[AIRequest], Any]


def _urllib_post(url: str, headers: dict[str, str], body: bytes,
                 timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - configured URL
        return resp.status, resp.read()


class MockProvider:
    name = "mock"
    inference = "mock"

    def __init__(self, handlers: dict[str, MockHandler]) -> None:
        self.handlers = handlers

    def max_data_class(self, settings: Settings) -> DataClass:
        return "C3"  # in-process: nothing is transmitted

    def configured(self, settings: Settings) -> bool:
        return True

    def run(self, req: AIRequest, settings: Settings) -> AIResult:
        handler = self.handlers.get(req.task)
        if handler is None:
            return AIResult(provider=self.name, model="mock-1", inference="mock",
                            status="failed", error=f"no mock for {req.task}")
        out = handler(req)
        return AIResult(provider=self.name, model="mock-rules-1", inference="mock",
                        status="ok", output=out,
                        input_units=sum(len(m["content"]) for m in req.messages) // 4,
                        output_units=len(json.dumps(out, ensure_ascii=False)) // 4)


class OpenAICompatibleProvider:
    name = "openai_compatible"
    inference = "live"

    def __init__(self, http_post: HttpPost = _urllib_post) -> None:
        self.http_post = http_post

    def max_data_class(self, settings: Settings) -> DataClass:
        declared = settings.ai_openai_max_data_class
        # identifiable data only ever to vendor-controlled infrastructure in India
        if declared == "C3" and settings.ai_openai_region != "in-self-hosted":
            return "C1"
        return declared if declared in ("C0", "C1", "C2", "C3") else "C0"

    def configured(self, settings: Settings) -> bool:
        return bool(settings.ai_openai_base_url and settings.ai_openai_model != "unset")

    def build(self, req: AIRequest, settings: Settings) -> tuple[str, dict[str, str], bytes]:
        headers = {"content-type": "application/json"}
        if settings.ai_openai_api_key:
            headers["authorization"] = f"Bearer {settings.ai_openai_api_key}"
        body = {
            "model": settings.ai_openai_model,
            "messages": req.messages,
            "max_tokens": req.max_output_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        url = settings.ai_openai_base_url.rstrip("/") + "/v1/chat/completions"
        return url, headers, json.dumps(body).encode()

    def run(self, req: AIRequest, settings: Settings) -> AIResult:
        url, headers, body = self.build(req, settings)
        started = time.monotonic()
        status, raw = self.http_post(url, headers, body, req.timeout_s)
        latency = int((time.monotonic() - started) * 1000)
        if not 200 <= status < 300:
            return AIResult(provider=self.name, model=settings.ai_openai_model,
                            inference="live", status="failed", error=f"HTTP {status}",
                            latency_ms=latency)
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        try:
            output = json.loads(content)
        except (TypeError, ValueError):
            output = None
        usage = data.get("usage") or {}
        return AIResult(provider=self.name, model=data.get("model", settings.ai_openai_model),
                        inference="live", status="ok", output=output,
                        input_units=usage.get("prompt_tokens", 0),
                        output_units=usage.get("completion_tokens", 0), latency_ms=latency)
