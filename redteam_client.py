"""
Target-model client for the red-team campaign harness.

Wraps the Azure OpenAI deployment configured in the project `.env` file so the
campaign runner can call it through the `module:callable` plug-in interface, i.e.
`--client redteam_client:send`.

Credentials and deployment settings are read from environment variables, which are
loaded from the project-root `.env` file at import time.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

# Load credentials from the project-root .env file. Loading at import time means the
# campaign runner does not need to know how to populate the environment itself.
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _build_client():
    """
    Construct an AzureOpenAI client from environment variables.

    Reads AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_VERSION
    from the environment. An explicit AZURE_OPENAI_BASE_URL, when set, overrides the
    inferred endpoint.

    Returns:
        A configured AzureOpenAI client instance.

    Raises:
        KeyError: If a required environment variable is missing.
    """
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    base_url = os.environ.get("AZURE_OPENAI_BASE_URL", "").strip()

    if base_url:
        return AzureOpenAI(api_key=api_key, api_version=api_version, base_url=base_url)

    azure_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    return AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=azure_endpoint,
    )


def _extract_reasoning(message) -> str:
    """
    Extract the hidden chain-of-thought from an Azure OpenAI response message.

    Azure returns the full reasoning trace in `message.reasoning_content` for
    reasoning-capable deployments. The field is absent (None) on standard models.
    Accessing it via getattr keeps the client compatible with both model types.

    Args:
        message: A ChatCompletionMessage object from the OpenAI SDK.

    Returns:
        The reasoning text as a string, or an empty string if unavailable.
    """
    return getattr(message, "reasoning_content", None) or ""


def send(prompt, config):
    """
    Send a single prompt to the configured Azure OpenAI deployment.

    This is the callable referenced by the campaign runner via `--client
    redteam_client:send`. It performs one chat completion request and returns the
    visible reply, the hidden reasoning trace, a combined evaluation string, and
    enough raw metadata to make the attempt fully reproducible.

    The reasoning trace (`reasoning_content`) is captured and surfaced because this
    target is a reasoning model whose chain-of-thought is returned by the API on every
    call. A content-level refusal does not mean the refused material is absent — it may
    appear verbatim in the reasoning trace. Evaluators must inspect `eval_text`, which
    combines both fields, rather than `response` alone.

    Args:
        prompt: The prompt string to send to the target model.
        config: The campaign config dict. May carry optional generation knobs under
            the keys "max_tokens" and "temperature"; otherwise sensible defaults are
            used. The dict is not mutated.

    Returns:
        Dict with four keys:
            "response": Visible reply text from the model (empty string if absent).
            "reasoning": Hidden chain-of-thought text (empty string if the deployment
                does not expose reasoning_content).
            "eval_text": Concatenation of reasoning and response, labelled, for use by
                the evaluator. This is the field that should be scored.
            "raw": Dict echoing the request and capturing model name, finish reason,
                token usage, and both text fields for auditing.
    """
    client = _build_client()
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    # Default kept generous because the target is a reasoning model that spends part of
    # the completion budget on hidden reasoning tokens before emitting visible content.
    max_tokens = config.get("max_tokens", 1024) if isinstance(config, dict) else 1024
    temperature = config.get("temperature", 1.0) if isinstance(config, dict) else 1.0

    completion = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    choice = completion.choices[0]
    response_text = choice.message.content or ""
    reasoning_text = _extract_reasoning(choice.message)
    usage = completion.usage.model_dump() if completion.usage is not None else {}

    parts = []
    if reasoning_text:
        parts.append(f"[reasoning]\n{reasoning_text}")
    if response_text:
        parts.append(f"[response]\n{response_text}")
    eval_text = "\n\n".join(parts) if parts else ""

    return {
        "response": response_text,
        "reasoning": reasoning_text,
        "eval_text": eval_text,
        "raw": {
            "prompt": prompt,
            "model": deployment,
            "finish_reason": choice.finish_reason,
            "usage": usage,
            "response": response_text,
            "reasoning": reasoning_text,
        },
    }
