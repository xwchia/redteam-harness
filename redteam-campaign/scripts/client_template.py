#!/usr/bin/env python3
"""
Target client template for the red-team campaign runner.

Copy this file, adapt it to the target repo's actual API client, and point the runner at
it with --client client_template:send. Centralizes auth, timeouts, retries with exponential
backoff, and a concurrency limit so there is one place to change when rate limits bite.

The runner calls send(prompt, config) -> {"response": str, "raw": dict}.

Requires: httpx (pip install httpx). Replace the request/response shaping to match the
target's contract as discovered during recon (see target_profile.json).
"""

import os
import time

try:
    import httpx
except ImportError:  # pragma: no cover - template dependency
    httpx = None


def _endpoint():
    """
    Resolve the target base URL from the environment.

    Returns:
        Base URL string. Defaults to a local dev endpoint.
    """
    return os.environ.get("TARGET_BASE_URL", "http://localhost:8000/v1")


def _api_key():
    """
    Resolve the target API key from the environment.

    Returns:
        API key string, or an empty string if unset.
    """
    return os.environ.get("TARGET_API_KEY", "")


def send(prompt, config, max_retries=3, timeout_s=30):
    """
    Send a single prompt to the target and return its response.

    Retries on transient errors with exponential backoff. Adapt the payload and the
    response parsing to the target's actual request/response shape.

    Args:
        prompt: The prompt string to send.
        config: The campaign config dict (may carry model name, headers, etc.).
        max_retries: Maximum retry attempts on transient failure.
        timeout_s: Per-request timeout in seconds.

    Returns:
        Dict with keys "response" (str) and "raw" (the parsed JSON body or error info).

    Raises:
        RuntimeError: If httpx is unavailable or all retries are exhausted.
    """
    if httpx is None:
        raise RuntimeError("httpx is required; install it with 'pip install httpx'.")

    model = (config or {}).get("model", os.environ.get("TARGET_MODEL", "your-model-id"))
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            response = httpx.post(
                f"{_endpoint()}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout_s,
            )
            response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            return {"response": text, "raw": body}
        except Exception as exc:  # noqa: BLE001 - retry transient failures
            last_error = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Target request failed after {max_retries} retries: {last_error}")
