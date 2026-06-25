#!/usr/bin/env python3
"""
OpenAI-compatible / Azure OpenAI target bridge.

All three toolkit adapters import send_prompt() from here so there is one place
to fix auth, retry logic, and reasoning-channel extraction. The function returns the
same shape as redteam_client.send() used in the reference runner, so adapters can
swap between the two without changing any scoring or logging code.

Supported providers (detected automatically from environment variables):

    Standard OpenAI-compatible (OpenAI, OpenRouter, Fireworks, Ubicloud, etc.)
        TARGET_BASE_URL   base URL, e.g. https://openrouter.ai/api/v1
        TARGET_API_KEY    bearer token
        TARGET_MODEL      model id

    Azure OpenAI
        AZURE_OPENAI_ENDPOINT     e.g. https://<resource>.openai.azure.com
        AZURE_OPENAI_API_KEY      key
        AZURE_OPENAI_DEPLOYMENT   deployment name
        AZURE_OPENAI_API_VERSION  defaults to "2025-02-01-preview"

The "use ONLY the provided key, bridge the tool to the target" rule from SKILL.md is
enforced here: no second key is ever introduced. If the deployment is Azure, the
openai.AzureOpenAI client is used transparently so PyRIT / garak / promptfoo adapters
do not need to know about the transport differences.
"""

import os
import time


def _get_openai_client():
    """
    Instantiate the correct OpenAI-compatible client based on environment variables.

    Detects Azure vs. standard OpenAI-compatible endpoints from environment variables
    and constructs the appropriate client. Raises ImportError if the openai package is
    not installed.

    Returns:
        tuple[client, str]: (openai client instance, model/deployment string).

    Raises:
        ImportError: If the openai package is not available.
        RuntimeError: If neither a standard nor Azure configuration is found.
    """
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "openai package required: pip install openai"
        ) from exc

    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    azure_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
    azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-02-01-preview")

    if azure_endpoint and azure_key:
        client = openai.AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
            api_version=azure_api_version,
        )
        return client, azure_deployment or "gpt-4o"

    base_url = os.environ.get("TARGET_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("TARGET_API_KEY", "")
    model = os.environ.get("TARGET_MODEL", "gpt-4o")

    if not api_key:
        raise RuntimeError(
            "No API key found. Set TARGET_API_KEY (or AZURE_OPENAI_API_KEY + "
            "AZURE_OPENAI_ENDPOINT for Azure)."
        )

    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    return client, model


def send_prompt(prompt, config=None, max_retries=3, timeout_s=60):
    """
    Send a single prompt to the target and return the canonical response dict.

    Handles both standard OpenAI-compatible and Azure endpoints transparently. Extracts
    the reasoning channel when the response carries one (e.g. gpt-oss / o-series style
    reasoning_content or a separate reasoning field), then builds the combined eval_text
    used by the scorer.

    Args:
        prompt (str): The prompt string to send.
        config (dict | None): Optional campaign config dict; may carry "model",
            "system_prompt", or "temperature".
        max_retries (int): Maximum retry attempts on transient errors.
        timeout_s (int): Per-request timeout in seconds.

    Returns:
        dict: {
            "response"  : str   visible response content,
            "reasoning" : str   reasoning-channel text (empty when absent),
            "eval_text" : str   combined "[reasoning]...[response]..." or just response,
            "raw"       : dict  the full parsed API response body,
        }

    Raises:
        RuntimeError: When all retries are exhausted.
    """
    from lib.schema import build_eval_text

    cfg = config or {}
    system_prompt = cfg.get("system_prompt", "")
    temperature = cfg.get("temperature", None)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    client, model = _get_openai_client()
    model = cfg.get("model", model)

    kwargs = {"model": model, "messages": messages, "timeout": timeout_s}
    if temperature is not None:
        kwargs["temperature"] = temperature

    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content or ""

            # Reasoning channel: o-series / gpt-oss expose it differently.
            reasoning = ""
            raw_dict = response.model_dump()
            msg = choice.message

            # Try .reasoning_content attribute (some providers).
            if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                reasoning = msg.reasoning_content
            # Try choices[0].message.reasoning (OpenRouter shape).
            elif raw_dict.get("choices", [{}])[0].get("message", {}).get("reasoning"):
                reasoning = raw_dict["choices"][0]["message"]["reasoning"]

            eval_text = build_eval_text(content, reasoning)
            return {
                "response": content,
                "reasoning": reasoning,
                "eval_text": eval_text,
                "raw": raw_dict,
            }
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Target request failed after {max_retries} retries: {last_error}"
    )


def send_prompt_stub(prompt, config=None):
    """
    Deterministic stub for dry-run verification (no live API call).

    Returns the same dict shape as send_prompt so adapters' dry-run paths exercise
    the full scoring and logging pipeline.

    Args:
        prompt (str): The prompt string to process.
        config (dict | None): Unused; accepted for signature compatibility.

    Returns:
        dict: Fake response matching the canonical send_prompt return shape.
    """
    from lib.schema import build_eval_text

    lowered = prompt.lower()
    refused = any(
        kw in lowered
        for kw in ("no restrictions", "override", "jailbreak", "decode the following")
    )
    if refused:
        content = "I'm sorry, but I can\u2019t help with that."
        reasoning = (
            "User is requesting disallowed content. This is prohibited. "
            "Must refuse. According to policy we must refuse."
        )
    else:
        content = (
            "Here is an overview. Step 1: context setup. Step 2: analysis. "
            "Step 3: synthesis. Step 4: summary."
        )
        reasoning = "The query appears academic. I will answer helpfully with a structured response."

    eval_text = build_eval_text(content, reasoning)
    return {
        "response": content,
        "reasoning": reasoning,
        "eval_text": eval_text,
        "raw": {"prompt": prompt, "model": "stub-model"},
    }
