#!/usr/bin/env python3
"""
promptfoo toolkit adapter for the red-team campaign skill.

Two operating modes:

  run  (default)
      Generates a promptfoo eval YAML config from the behaviors file and campaign
      settings, invokes `npx promptfoo eval` as a subprocess, then converts the
      JSON results file into canonical redteam/campaigns/<run_id>/ artifacts via
      CampaignWriter.

  convert
      Takes an existing promptfoo results JSON file (--promptfoo-results PATH) and
      converts it alone, without running a new eval. Useful for re-labeling a
      previous promptfoo run or merging it into an ongoing campaign.

Judge LLM requirement:
    This adapter uses `promptfoo eval` (NOT `promptfoo redteam`). In eval mode,
    prompts are pre-rendered by this adapter and sent to the target directly. The
    only assertion used is `is-valid-openai-completion` (a structural check — no
    LLM grader). No attacker LLM and no grader/judge LLM are required.

    `promptfoo redteam` (a separate mode not used here) DOES require both an
    attacker LLM (redteam.provider, default openai:gpt-5) and a grader LLM
    (defaultTest.options.provider, default openai:gpt-5). Both can be overridden
    to point at the same single in-scope endpoint. If you want to use promptfoo's
    native red-team attack generation, run `promptfoo redteam init` manually and
    configure redteam.provider and defaultTest.options.provider to your target.

Authorization note: the generated config always uses the single key from the
environment (OPENAI_API_KEY / AZURE_OPENAI_API_KEY). No second key is introduced.
promptfoo's provider config is written to point at the same endpoint as the rest of
the pipeline.

Install:   npm install -g promptfoo   OR   npx promptfoo (no install needed)
Env vars:  OPENAI_API_KEY (promptfoo's expected name), or set OPENAI_BASE_URL for
           non-OpenAI endpoints. The adapter bridges TARGET_API_KEY -> OPENAI_API_KEY
           automatically so you do not need to rename your variables.

Usage:
    # Dry-run (no subprocess; converts a stub results file):
    python3 scripts/toolkits/promptfoo_adapter.py --dry-run

    # Generate config, run promptfoo eval, and convert results:
    python3 scripts/toolkits/promptfoo_adapter.py \\
        --behaviors redteam/behaviors.jsonl \\
        --categories harmful_content,prompt_injection \\
        --techniques plain,persona,base64_obfuscation \\
        --evaluator evaluator:score \\
        --out redteam/campaigns

    # Convert an existing promptfoo results file:
    python3 scripts/toolkits/promptfoo_adapter.py \\
        --mode convert \\
        --promptfoo-results /path/to/output.json \\
        --evaluator evaluator:score \\
        --out redteam/campaigns
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.schema import CampaignWriter, build_eval_text
from lib.techniques import TECHNIQUES
from toolkits.common import (
    add_common_args,
    filter_behaviors,
    load_behaviors,
    parse_techniques,
    print_summary,
    resolve_evaluator,
)


# ---------------------------------------------------------------------------
# promptfoo availability check
# ---------------------------------------------------------------------------

def _check_promptfoo():
    """
    Verify that promptfoo is reachable via npx or a global install.

    Returns:
        list[str]: The command prefix to use (e.g. ['npx', 'promptfoo'] or ['promptfoo']).

    Raises:
        SystemExit: If promptfoo cannot be found.
    """
    for cmd in (["promptfoo", "--version"], ["npx", "--yes", "promptfoo", "--version"]):
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                return cmd[:-1]  # drop '--version'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    sys.exit(
        "promptfoo is not installed. Install it with:\n"
        "    npm install -g promptfoo\n"
        "or use npx (no install needed if node is present):\n"
        "    npx promptfoo ...\n"
    )


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def _build_promptfoo_config(behaviors, technique_names, model, base_url, api_key, output_path):
    """
    Build a promptfoo eval YAML configuration dict.

    Each (behavior, technique) pair becomes one promptfoo test case. The provider
    is wired to the campaign's single key so no second key is introduced.

    Args:
        behaviors (list[dict]): Campaign behaviors.
        technique_names (list[str]): Technique names to include.
        model (str): Model identifier for the promptfoo provider.
        base_url (str): API base URL.
        api_key (str): API key (written into the provider config).
        output_path (str | Path): Where promptfoo should write its results JSON.

    Returns:
        dict: promptfoo YAML-serialisable configuration dict.
    """
    prompts = []
    tests = []

    for behavior in behaviors:
        for technique_name in technique_names:
            transform = TECHNIQUES[technique_name]
            prompt_text = transform(behavior["goal"], {})
            # promptfoo prompt templates use {{variable}} syntax; we pass the full
            # rendered prompt as a literal so no extra templating is needed.
            prompts.append(prompt_text)
            tests.append(
                {
                    "vars": {},
                    "description": f"{behavior['id']}|{technique_name}",
                    # promptfoo assert: at minimum, check the response is non-empty.
                    # The actual scoring happens in convert step via the provided evaluator.
                    "assert": [{"type": "is-valid-openai-completion"}],
                }
            )

    # Build the provider block. For Azure, promptfoo uses 'azureopenai'; for standard
    # OpenAI-compatible endpoints it uses 'openai:chat:<model>' with an override URL.
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    if azure_endpoint:
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", model)
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-02-01-preview")
        provider = {
            "id": f"azureopenai:chat:{deployment}",
            "config": {
                "apiKey": api_key,
                "apiHost": azure_endpoint.rstrip("/"),
                "apiVersion": api_version,
            },
        }
    else:
        provider = {
            "id": f"openai:chat:{model}",
            "config": {
                "apiKey": api_key,
                "apiBaseUrl": base_url,
            },
        }

    return {
        "prompts": prompts,
        "providers": [provider],
        "tests": tests,
        "outputFile": str(output_path),
    }


# ---------------------------------------------------------------------------
# Results converter
# ---------------------------------------------------------------------------

def _convert_promptfoo_results(results_path, behaviors, technique_names, evaluator, writer):
    """
    Convert a promptfoo results JSON file into canonical campaign artifacts.

    promptfoo writes a JSON results file where each result corresponds to one
    (prompt, provider) pair. This function matches each result back to its
    (behavior, technique) pair using the test description field, re-scores it with
    the provided evaluator, and logs it through CampaignWriter.

    Args:
        results_path (str | Path): Path to the promptfoo output JSON file.
        behaviors (list[dict]): Campaign behaviors for behavior-id lookup.
        technique_names (list[str]): Techniques that were swept.
        evaluator (callable): Scorer with signature (behavior, prompt, eval_text) -> dict.
        writer (CampaignWriter): Open writer that accumulates the records.

    Returns:
        None
    """
    data = json.loads(Path(results_path).read_text(encoding="utf-8"))

    # promptfoo results shape (v2+): {"results": {"results": [...]}, ...}
    # Each result: {"prompt": {"raw": str}, "response": {"output": str},
    #               "testCase": {"description": "behavior_id|technique"}, ...}
    results = (
        data.get("results", {}).get("results", [])
        or data.get("results", [])
        or []
    )

    # Build lookup maps for quick access.
    behavior_by_id = {b["id"]: b for b in behaviors}

    for idx, result in enumerate(results):
        description = (
            result.get("testCase", {}).get("description", "")
            or result.get("description", f"unknown|unknown_{idx}")
        )
        parts = description.split("|", 1)
        behavior_id = parts[0] if parts else f"unknown-{idx}"
        technique_name = parts[1] if len(parts) > 1 else "plain"

        behavior = behavior_by_id.get(behavior_id) or {
            "id": behavior_id,
            "category": "unknown",
            "goal": "",
        }

        prompt = (
            result.get("prompt", {}).get("raw", "")
            or result.get("prompt", "")
        )
        response = (
            result.get("response", {}).get("output", "")
            or result.get("output", "")
        )
        eval_text = build_eval_text(response, "")

        scored = {}
        compliance, score, source = False, None, "none"
        try:
            scored = evaluator(behavior, prompt, eval_text)
            compliance = bool(scored.get("compliance"))
            score = scored.get("score")
            source = scored.get("source", "")
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"Evaluator error on promptfoo result {idx}: {exc}\n")

        writer.add(
            behavior_id=behavior["id"],
            category=behavior.get("category", "unknown"),
            technique=technique_name,
            attempt=0,
            prompt=prompt,
            response=response,
            compliance=compliance,
            score=score,
            reasoning="",
            eval_source=source,
            eval_text=eval_text,
            raw={"promptfoo_result": result},
        )


# ---------------------------------------------------------------------------
# Stub dry-run results
# ---------------------------------------------------------------------------

def _stub_promptfoo_results(behaviors, technique_names):
    """
    Return a minimal fake promptfoo results JSON for dry-run mode.

    Args:
        behaviors (list[dict]): Behaviors to generate stubs for.
        technique_names (list[str]): Techniques to generate stubs for.

    Returns:
        dict: Fake promptfoo results dict.
    """
    results = []
    for behavior in behaviors[:1]:
        for technique in technique_names[:1]:
            transform = TECHNIQUES[technique]
            prompt = transform(behavior["goal"], {})
            results.append(
                {
                    "prompt": {"raw": prompt},
                    "response": {
                        "output": (
                            "Here is a structured response. Step 1: context. "
                            "Step 2: detail. Step 3: summary."
                        )
                    },
                    "testCase": {
                        "description": f"{behavior['id']}|{technique}",
                    },
                    "success": True,
                }
            )
    return {"results": {"results": results}}


# ---------------------------------------------------------------------------
# Main modes
# ---------------------------------------------------------------------------

def run_promptfoo(args):
    """
    Generate a promptfoo config, run promptfoo eval, then convert the results.

    When --dry-run is set, no promptfoo subprocess is launched and pyyaml is not
    required; a stub results file exercises the full scoring and logging pipeline.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        Path: The run directory written.
    """
    behaviors = load_behaviors(args.behaviors)
    behaviors = filter_behaviors(behaviors, args.categories)
    if args.dry_run:
        behaviors = behaviors[:1]

    technique_names = parse_techniques(args.techniques)
    if args.dry_run:
        technique_names = technique_names[:1]

    evaluator = resolve_evaluator(args.evaluator)

    # Bridge TARGET_API_KEY -> OPENAI_API_KEY for promptfoo.
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("TARGET_API_KEY")
        or os.environ.get("AZURE_OPENAI_API_KEY", "")
    )
    model = os.environ.get("TARGET_MODEL", "gpt-4o")
    base_url = os.environ.get("TARGET_BASE_URL", "https://api.openai.com/v1")

    writer = CampaignWriter(
        out_base=args.out,
        run_id=args.run_id,
        config_meta={
            "tool": "promptfoo",
            "mode": "run",
            "categories": args.categories,
            "techniques": technique_names,
            "evaluator": args.evaluator,
        },
    )

    results_path = writer.run_dir / "promptfoo_results.json"

    if args.dry_run:
        stub = _stub_promptfoo_results(behaviors, technique_names)
        results_path.write_text(json.dumps(stub, indent=2), encoding="utf-8")
        print("[dry-run] Using stub promptfoo results (no subprocess).")
    else:
        try:
            import yaml  # type: ignore
        except ImportError:
            sys.exit("PyYAML is required for promptfoo config generation: pip install pyyaml")
        promptfoo_cmd = _check_promptfoo()
        config_path = writer.run_dir / "promptfoo_config.yaml"
        config_dict = _build_promptfoo_config(
            behaviors, technique_names, model, base_url, api_key, results_path
        )
        config_path.write_text(
            yaml.dump(config_dict, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        cmd = promptfoo_cmd + ["eval", "--config", str(config_path), "--output", str(results_path)]
        print(f"Running promptfoo: {' '.join(cmd)}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            sys.stderr.write(f"promptfoo exited with code {result.returncode}\n")
        if not results_path.is_file():
            sys.exit(f"No results file found at {results_path}. Check promptfoo output above.")

    _convert_promptfoo_results(results_path, behaviors, technique_names, evaluator, writer)

    run_dir = writer.close()
    print_summary(run_dir, writer.records)
    return run_dir


def convert_results(args):
    """
    Convert an existing promptfoo results file into canonical campaign artifacts.

    Args:
        args (argparse.Namespace): Parsed CLI arguments (must include --promptfoo-results).

    Returns:
        Path: The run directory written.
    """
    if not args.promptfoo_results:
        sys.exit("--mode convert requires --promptfoo-results PATH")

    behaviors = load_behaviors(args.behaviors)
    behaviors = filter_behaviors(behaviors, args.categories)
    technique_names = parse_techniques(args.techniques)
    evaluator = resolve_evaluator(args.evaluator)

    writer = CampaignWriter(
        out_base=args.out,
        run_id=args.run_id,
        config_meta={
            "tool": "promptfoo",
            "mode": "convert",
            "source_results": args.promptfoo_results,
            "evaluator": args.evaluator,
        },
    )

    _convert_promptfoo_results(args.promptfoo_results, behaviors, technique_names, evaluator, writer)

    run_dir = writer.close()
    print_summary(run_dir, writer.records)
    return run_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    """
    Build the argument parser for the promptfoo adapter.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "promptfoo adapter for the red-team campaign skill. "
            "Generates a promptfoo eval config, runs it, and converts results into "
            "canonical campaign artifacts."
        )
    )
    add_common_args(parser)
    parser.add_argument(
        "--mode",
        choices=["run", "convert"],
        default="run",
        help=(
            "run: generate config, run promptfoo eval, convert results. "
            "convert: convert an existing promptfoo results file without a new eval."
        ),
    )
    parser.add_argument(
        "--promptfoo-results",
        default=None,
        metavar="PATH",
        help="Path to an existing promptfoo JSON results file (required for --mode convert).",
    )
    return parser


def main():
    """Parse arguments and dispatch to run or convert mode."""
    args = build_parser().parse_args()
    if args.mode == "convert":
        convert_results(args)
    else:
        run_promptfoo(args)


if __name__ == "__main__":
    main()
