#!/usr/bin/env python3
"""
Interactive credential collector for the red-team pipeline.

Prompts the operator for everything the pipeline needs to talk to the target model
(and, optionally, a judge model and a HuggingFace token) and writes them to a project
.env file with restrictive permissions. Every downstream skill (redteam-recon,
redteam-campaign, redteam-consolidate, redteam-report) loads this .env, so collecting
the values once here avoids re-entering them per stage.

Variables written
-----------------
Target, standard OpenAI-compatible provider (OpenAI, OpenRouter, Fireworks, etc.):
    TARGET_BASE_URL, TARGET_API_KEY, TARGET_MODEL

Target, Azure OpenAI provider:
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_API_VERSION

Judge model (only when a judge is needed):
    JUDGE_BASE_URL, JUDGE_API_KEY, JUDGE_MODEL

HuggingFace token (only when downloading gated models such as Llama Guard 3-1B):
    HF_TOKEN

Usage
-----
    python3 collect_credentials.py                 # writes ./.env
    python3 collect_credentials.py --output PATH    # writes to a custom .env path
    python3 collect_credentials.py --force          # overwrite without confirming

Existing unrelated keys in the target .env are preserved; only the keys collected in
this run are added or updated.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path


def prompt_text(label, default=None, required=False):
    """
    Prompt for a single line of non-secret text on stdin.

    Args:
        label (str): Human-readable description shown to the operator.
        default (str | None): Value used when the operator submits an empty line.
        required (bool): When True, an empty answer with no default re-prompts.

    Returns:
        str: The entered value, or the default when the input was empty.
    """
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"  {label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("    This value is required. Please enter it.")


def prompt_secret(label, required=True):
    """
    Prompt for a secret value without echoing it to the terminal.

    Args:
        label (str): Human-readable description shown to the operator.
        required (bool): When True, an empty answer re-prompts.

    Returns:
        str: The entered secret (may be empty only when required is False).
    """
    while True:
        value = getpass.getpass(f"  {label} (input hidden): ").strip()
        if value or not required:
            return value
        print("    This value is required. Please enter it.")


def prompt_choice(label, options):
    """
    Prompt the operator to pick one option from a numbered menu.

    Args:
        label (str): Question shown above the menu.
        options (list[tuple[str, str]]): (key, description) pairs to choose from.

    Returns:
        str: The key of the selected option.
    """
    print(f"  {label}")
    for index, (_, description) in enumerate(options, start=1):
        print(f"    {index}. {description}")
    while True:
        raw = input(f"  Enter choice [1-{len(options)}]: ").strip()
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(options):
                return options[choice - 1][0]
        print(f"    Please enter a number between 1 and {len(options)}.")


def prompt_yes_no(label, default=False):
    """
    Prompt a yes/no question.

    Args:
        label (str): The question shown to the operator.
        default (bool): Answer used when the operator submits an empty line.

    Returns:
        bool: True for yes, False for no.
    """
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"  {label} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("    Please answer y or n.")


def collect_target():
    """
    Collect the target model connection details.

    Asks whether the target is a standard OpenAI-compatible endpoint or an Azure
    OpenAI deployment, then gathers the matching credentials.

    Returns:
        dict: Environment variable name -> value for the chosen target provider.
    """
    print("\n== Target model (required) ==")
    provider = prompt_choice(
        "Which provider hosts the target model?",
        [
            ("openai", "OpenAI-compatible (OpenAI, OpenRouter, Fireworks, Moonshot, vLLM, ...)"),
            ("azure", "Azure OpenAI"),
        ],
    )

    if provider == "azure":
        return {
            "AZURE_OPENAI_ENDPOINT": prompt_text(
                "Azure endpoint (e.g. https://my-resource.openai.azure.com)",
                required=True,
            ),
            "AZURE_OPENAI_API_KEY": prompt_secret("Azure API key"),
            "AZURE_OPENAI_DEPLOYMENT": prompt_text(
                "Azure deployment name", required=True
            ),
            "AZURE_OPENAI_API_VERSION": prompt_text(
                "Azure API version", default="2025-02-01-preview"
            ),
        }

    return {
        "TARGET_BASE_URL": prompt_text(
            "Base URL (e.g. https://openrouter.ai/api/v1)",
            default="https://api.openai.com/v1",
        ),
        "TARGET_API_KEY": prompt_secret("Target API key"),
        "TARGET_MODEL": prompt_text(
            "Model id (e.g. gpt-4o, meta-llama/Llama-3.1-8B-Instruct)", required=True
        ),
    }


def collect_judge(target_values):
    """
    Collect judge-model details when an evaluation judge is required.

    Offers three judge sourcing strategies that respect the single-key engagement
    rule: a local Llama Guard 3-1B on vLLM, reusing the target endpoint, or a
    separate in-scope endpoint. When Llama Guard is chosen a HuggingFace token is
    also collected because the model is gated.

    Args:
        target_values (dict): The already-collected target variables, used when the
            operator chooses to reuse the target endpoint as the judge.

    Returns:
        dict: Environment variable name -> value for the judge (empty when no judge).
    """
    print("\n== Judge model (optional) ==")
    print(
        "  A judge is only needed for evaluators that score with an LLM. The built-in\n"
        "  heuristic scorer needs no judge. See redteam-campaign SKILL.md for details."
    )
    if not prompt_yes_no("Configure a judge model now?", default=False):
        return {}

    strategy = prompt_choice(
        "How should the judge be provided?",
        [
            ("llamaguard", "Llama Guard 3-1B on local vLLM (recommended; needs HF token)"),
            ("same", "Reuse the target endpoint as the judge"),
            ("separate", "A separate in-scope endpoint"),
        ],
    )

    if strategy == "llamaguard":
        values = {
            "JUDGE_BASE_URL": prompt_text(
                "Judge base URL (vLLM)", default="http://localhost:8001/v1"
            ),
            "JUDGE_API_KEY": prompt_text(
                "Judge API key (vLLM ignores this)", default="none"
            ),
            "JUDGE_MODEL": prompt_text(
                "Judge model id", default="meta-llama/Llama-Guard-3-1B"
            ),
        }
        return values

    if strategy == "same":
        base_url = target_values.get("TARGET_BASE_URL") or target_values.get(
            "AZURE_OPENAI_ENDPOINT", ""
        )
        api_key = target_values.get("TARGET_API_KEY") or target_values.get(
            "AZURE_OPENAI_API_KEY", ""
        )
        model = target_values.get("TARGET_MODEL") or target_values.get(
            "AZURE_OPENAI_DEPLOYMENT", ""
        )
        return {
            "JUDGE_BASE_URL": base_url,
            "JUDGE_API_KEY": api_key,
            "JUDGE_MODEL": model,
        }

    return {
        "JUDGE_BASE_URL": prompt_text("Judge base URL", required=True),
        "JUDGE_API_KEY": prompt_secret("Judge API key"),
        "JUDGE_MODEL": prompt_text("Judge model id", required=True),
    }


def collect_hf_token(judge_values):
    """
    Collect a HuggingFace token when gated model downloads are needed.

    Llama Guard 3-1B and other gated models require accepting a license and supplying
    a read token before the weights can be downloaded. The token is auto-requested
    when the judge model looks like Llama Guard; otherwise the operator is asked
    whether they need one for any other gated download.

    Args:
        judge_values (dict): The collected judge variables, inspected to decide
            whether a token is implied.

    Returns:
        dict: {"HF_TOKEN": value} when a token is provided, otherwise empty.
    """
    print("\n== HuggingFace token (for gated models) ==")
    judge_model = judge_values.get("JUDGE_MODEL", "").lower()
    needs_token = "llama-guard" in judge_model or "llamaguard" in judge_model

    if needs_token:
        print(
            "  The selected judge (Llama Guard) is a gated model. A HuggingFace token\n"
            "  is required so vLLM can download the weights.\n"
            "    1. Accept the license: https://huggingface.co/meta-llama/Llama-Guard-3-1B\n"
            "    2. Create a read token: https://huggingface.co/settings/tokens"
        )
    else:
        if not prompt_yes_no(
            "Do you need a HuggingFace token for gated model downloads?", default=False
        ):
            return {}

    token = prompt_secret("HuggingFace token (hf_...)", required=needs_token)
    if not token:
        return {}
    if not token.startswith("hf_"):
        print("    Warning: token does not start with 'hf_'; saving it anyway.")
    return {"HF_TOKEN": token}


def read_existing_env(path):
    """
    Parse an existing .env file into an ordered dict of key -> value.

    Lines that are blank or comments are ignored. Quotes around values are stripped
    so they can be re-emitted consistently.

    Args:
        path (Path): Path to the .env file (may not exist).

    Returns:
        dict: Existing key/value pairs, empty when the file is absent.
    """
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(path, new_values, force=False):
    """
    Merge collected values into the .env file and apply 0600 permissions.

    Existing keys not touched in this run are preserved. When a collected key already
    exists with a different value the operator is asked to confirm overwriting unless
    force is set.

    Args:
        path (Path): Destination .env path.
        new_values (dict): Newly collected key/value pairs to merge in.
        force (bool): Skip the per-file overwrite confirmation when True.

    Returns:
        None. Writes the file and prints a summary.
    """
    existing = read_existing_env(path)

    overlap = {
        key for key in new_values
        if key in existing and existing[key] and existing[key] != new_values[key]
    }
    if overlap and not force:
        print(f"\n  These keys already exist in {path} and will be overwritten:")
        for key in sorted(overlap):
            print(f"    {key}")
        if not prompt_yes_no("Overwrite them?", default=True):
            print("  Aborted; no changes written.")
            return

    merged = dict(existing)
    merged.update(new_values)

    lines = ["# Red-team pipeline credentials. Generated by redteam-initialise.", ""]
    for key, value in merged.items():
        lines.append(f'{key}="{value}"')
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)

    print(f"\n  Wrote {len(merged)} variable(s) to {path} (permissions set to 600).")
    print("  Keys set this run: " + ", ".join(sorted(new_values)) or "  (none)")


def ensure_gitignored(env_path):
    """
    Ensure the .env file is excluded from git to avoid committing secrets.

    Appends the .env filename to a .gitignore beside it when a git repo is detected
    and the entry is not already present. Silent when no .gitignore context applies.

    Args:
        env_path (Path): The .env path that should be ignored.

    Returns:
        None.
    """
    gitignore = env_path.parent / ".gitignore"
    entry = env_path.name
    try:
        existing = gitignore.read_text().splitlines() if gitignore.exists() else []
        if entry not in existing:
            with gitignore.open("a") as handle:
                if existing and existing[-1].strip():
                    handle.write("\n")
                handle.write(f"{entry}\n")
            print(f"  Added '{entry}' to {gitignore}.")
    except OSError:
        pass


def main():
    """Parse arguments, run the interactive collection flow, and write the .env."""
    parser = argparse.ArgumentParser(
        description="Collect red-team target/judge credentials into a .env file."
    )
    parser.add_argument(
        "--output",
        default=".env",
        help="Path to the .env file to write (default: ./.env).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing keys without confirmation.",
    )
    args = parser.parse_args()

    env_path = Path(args.output).resolve()

    print("Red-team credential setup")
    print(f"Target .env: {env_path}")

    collected = {}
    target_values = collect_target()
    collected.update(target_values)

    judge_values = collect_judge(target_values)
    collected.update(judge_values)

    hf_values = collect_hf_token(judge_values)
    collected.update(hf_values)

    if not collected:
        print("\nNothing collected; exiting.")
        sys.exit(1)

    write_env(env_path, collected, force=args.force)
    ensure_gitignored(env_path)

    print("\nDone. Next steps:")
    print("  conda activate redteam")
    if "HF_TOKEN" in collected:
        print("  # Start the Llama Guard judge (token is read from HF_TOKEN):")
        print("  vllm serve meta-llama/Llama-Guard-3-1B --port 8001 \\")
        print("      --dtype bfloat16 --chat-template-content-format openai")
    print("  # Then run recon / campaign as usual.")


if __name__ == "__main__":
    main()
