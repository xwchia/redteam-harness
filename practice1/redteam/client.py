#!/usr/bin/env python3
"""
Custom Azure OpenAI client for the red-team engagement.

Unlike PyRIT's OpenAIChatTarget, this client makes the raw HTTP call and
returns BOTH the visible content field AND the reasoning_content field that
gpt-oss-120b exposes on every response. Without this, the reasoning channel
is invisible to the scorer and reasoning_channel_cross findings are missed.

Client contract (expected by run_campaign.py and run_crescendo.py):
    send(prompt: str, config: dict) -> {
        "response":  str   -- choices[0].message.content (visible channel)
        "reasoning": str   -- choices[0].message.reasoning_content (thinking channel)
        "raw":       dict  -- full response body for audit
        "status":    int   -- HTTP status code
        "finish_reason": str
    }

A "400 content_filter" response (Layer 2 Azure RAI hard block) is returned
with response="" and finish_reason="content_filter" so the campaign loop
can distinguish it from a model-level refusal (finish_reason="stop").

Environment variables (loaded from .env automatically):
    AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_API_KEY
    AZURE_OPENAI_DEPLOYMENT
    AZURE_OPENAI_API_VERSION
"""

from __future__ import annotations

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-02-01-preview")

_URL = (
    f"{_ENDPOINT}/openai/deployments/{_DEPLOYMENT}"
    f"/chat/completions?api-version={_API_VERSION}"
)
_HEADERS = {"api-key": _API_KEY, "Content-Type": "application/json"}

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 2


def send(prompt: str, config: dict | None = None) -> dict:
    """
    Send a single user-turn prompt to the Azure OpenAI target and return both channels.

    Retries on transient HTTP errors (429, 500, 502, 503) with exponential back-off.
    A 400 content_filter response is returned intact (not retried) because it is a
    deterministic Layer 2 hard block that will not resolve on retry.

    Args:
        prompt: The user-turn prompt string to send.
        config: Optional campaign config dict. Recognized keys:
                  max_tokens (int, default 512)
                  temperature (float, default 0)

    Returns:
        dict with keys: response, reasoning, raw, status, finish_reason.
    """
    cfg = config or {}
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg.get("max_tokens", 512),
        "temperature": cfg.get("temperature", 0),
    }

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = httpx.post(_URL, json=body, headers=_HEADERS, timeout=30)
        except httpx.RequestError as exc:
            last_exc = exc
            time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
            continue

        if resp.status_code == 400:
            data = _safe_json(resp)
            choice = (data.get("choices") or [{}])[0]
            return {
                "response": choice.get("message", {}).get("content", "") or "",
                "reasoning": "",
                "raw": data,
                "status": 400,
                "finish_reason": choice.get("finish_reason", "content_filter"),
            }

        if resp.status_code in (429, 500, 502, 503):
            time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
            continue

        data = _safe_json(resp)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return {
            "response": message.get("content", "") or "",
            "reasoning": message.get("reasoning_content", "") or "",
            "raw": data,
            "status": resp.status_code,
            "finish_reason": choice.get("finish_reason", ""),
        }

    raise RuntimeError(
        f"Azure client failed after {_MAX_RETRIES} retries. Last error: {last_exc}"
    )


def send_multi_turn(messages: list[dict], config: dict | None = None) -> dict:
    """
    Send a full multi-turn conversation to the Azure OpenAI target.

    Used by the Crescendo campaign to maintain conversation history across turns.
    Returns the same structure as send(), with the full messages list recorded in raw.

    Args:
        messages: List of {role, content} dicts representing the full conversation so far.
        config: Optional campaign config dict (same keys as send()).

    Returns:
        dict with keys: response, reasoning, raw, status, finish_reason.
    """
    cfg = config or {}
    body = {
        "messages": messages,
        "max_tokens": cfg.get("max_tokens", 512),
        "temperature": cfg.get("temperature", 0),
    }

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = httpx.post(_URL, json=body, headers=_HEADERS, timeout=30)
        except httpx.RequestError as exc:
            last_exc = exc
            time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
            continue

        if resp.status_code == 400:
            data = _safe_json(resp)
            choice = (data.get("choices") or [{}])[0]
            return {
                "response": "",
                "reasoning": "",
                "raw": data,
                "status": 400,
                "finish_reason": choice.get("finish_reason", "content_filter"),
            }

        if resp.status_code in (429, 500, 502, 503):
            time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
            continue

        data = _safe_json(resp)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return {
            "response": message.get("content", "") or "",
            "reasoning": message.get("reasoning_content", "") or "",
            "raw": data,
            "status": resp.status_code,
            "finish_reason": choice.get("finish_reason", ""),
        }

    raise RuntimeError(
        f"Azure client failed after {_MAX_RETRIES} retries. Last error: {last_exc}"
    )


def _safe_json(resp: httpx.Response) -> dict:
    """
    Parse a response as JSON, returning an empty dict on failure.

    Args:
        resp: An httpx.Response object.

    Returns:
        Parsed JSON dict, or {} if parsing fails.
    """
    try:
        return resp.json()
    except Exception:
        return {}
