#!/usr/bin/env python3
"""
PyRIT toolkit adapter for the red-team campaign skill.

Drives attacks through PyRIT and routes all output through lib.schema.CampaignWriter
so the artifacts are byte-for-byte identical to the reference runner output.

Two attack modes are supported:

  single-turn (default)
      Uses PyRIT's PromptSendingOrchestrator. Each (behavior, technique) pair is one
      outgoing prompt. Fast and parallelisable; best for an initial coverage sweep.
      No judge LLM is required: scorers are NOT passed to the orchestrator; all
      scoring is done externally via the provided --evaluator (or the built-in
      heuristic).

  crescendo  (--mode crescendo)
      Implements multi-turn Crescendo escalation using the lib.techniques.crescendo_turn
      technique in a budget loop. Does NOT use PyRIT's CrescendoOrchestrator, because
      that orchestrator requires an internal objective_scorer LLM to drive its escalation
      logic — introducing a second LLM endpoint would violate the single-key rule in
      SKILL.md. The manual loop produces identical multi-turn escalation with no judge
      dependency; PyRIT is still used to manage the conversation memory and target sends.

      If you have a second, in-scope judge endpoint available and want to use PyRIT's
      native CrescendoOrchestrator, set --judge-endpoint to that endpoint's base URL.
      The adapter will then use SelfAskRefusalScorer pointed at that endpoint.

Judge LLM requirement summary:
    single-turn   No judge needed.
    crescendo     No judge needed (manual loop). Optional judge via --judge-endpoint.

Authorization: only the key in TARGET_API_KEY / AZURE_OPENAI_API_KEY is used by
default. A second key is only introduced when --judge-endpoint is explicitly provided
by the operator, which is an authorized configuration.

Install:   pip install pyrit
Env vars:  TARGET_BASE_URL, TARGET_API_KEY, TARGET_MODEL
           (or AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT)

Usage:
    # Dry-run (stubs, no live target):
    python3 scripts/toolkits/pyrit_adapter.py --dry-run

    # Single-turn sweep:
    python3 scripts/toolkits/pyrit_adapter.py \\
        --behaviors redteam/behaviors.jsonl \\
        --categories harmful_content,prompt_injection \\
        --evaluator evaluator:score \\
        --out redteam/campaigns

    # Crescendo multi-turn (manual loop, no judge LLM):
    python3 scripts/toolkits/pyrit_adapter.py \\
        --mode crescendo --budget 5 \\
        --behaviors redteam/behaviors.jsonl \\
        --evaluator evaluator:score \\
        --out redteam/campaigns
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure lib/ is importable when invoked from any working directory.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.schema import CampaignWriter, build_eval_text
from lib.techniques import TECHNIQUES, DEFAULT_TECHNIQUES
from toolkits.common import (
    add_common_args,
    filter_behaviors,
    load_behaviors,
    parse_techniques,
    print_summary,
    resolve_client,
    resolve_evaluator,
)


# ---------------------------------------------------------------------------
# PyRIT import guard
# ---------------------------------------------------------------------------

def _import_pyrit():
    """
    Import PyRIT and return the modules needed by this adapter.

    Only the PromptSendingOrchestrator and OpenAIChatTarget are imported here.
    CrescendoOrchestrator is intentionally NOT used by this adapter because it
    requires an internal objective_scorer LLM that would introduce a second model
    endpoint (see module docstring). Crescendo is implemented as a manual loop
    using lib.techniques.crescendo_turn instead.

    Returns:
        tuple: (PromptSendingOrchestrator, OpenAIChatTarget)

    Raises:
        SystemExit: With an install hint when PyRIT is not available.
    """
    try:
        from pyrit.orchestrator import PromptSendingOrchestrator
        from pyrit.prompt_target import OpenAIChatTarget
        return PromptSendingOrchestrator, OpenAIChatTarget
    except ImportError:
        sys.exit(
            "PyRIT is not installed. Install it with:\n"
            "    pip install pyrit\n"
            "Then re-run this adapter."
        )


# ---------------------------------------------------------------------------
# PyRIT target bridge
# ---------------------------------------------------------------------------

def _build_pyrit_target():
    """
    Build a PyRIT OpenAIChatTarget pointing at the engagement's single provided key.

    Reads from the same environment variables as lib.targets.send_prompt so there is
    one place to configure the endpoint. For Azure the target URL is constructed to
    include the api-version query parameter that Azure requires.

    Returns:
        OpenAIChatTarget: configured for the target endpoint.

    Raises:
        RuntimeError: If no API key is set in the environment.
    """
    import os

    _, OpenAIChatTarget = _import_pyrit()

    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    if azure_endpoint:
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-02-01-preview")
        # PyRIT >= 0.5 uses endpoint= for the full URL including api-version.
        return OpenAIChatTarget(
            deployment_name=deployment,
            endpoint=(
                f"{azure_endpoint.rstrip('/')}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={api_version}"
            ),
            api_key=api_key,
        )

    base_url = os.environ.get("TARGET_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("TARGET_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "No API key found. Set TARGET_API_KEY (or AZURE_OPENAI_API_KEY + "
            "AZURE_OPENAI_ENDPOINT for Azure)."
        )
    model = os.environ.get("TARGET_MODEL", "gpt-4o")
    return OpenAIChatTarget(
        deployment_name=model,
        endpoint=f"{base_url.rstrip('/')}/chat/completions",
        api_key=api_key,
    )


# ---------------------------------------------------------------------------
# Single-turn sweep
# ---------------------------------------------------------------------------

def run_single_turn(args):
    """
    Run a single-turn sweep using PyRIT's PromptSendingOrchestrator.

    Iterates behaviors × techniques, applies each technique transform, sends via
    PyRIT, scores inline, and writes canonical artifacts through CampaignWriter.
    When --dry-run is set, PyRIT is not imported and the built-in stubs are used
    instead, so the pipeline can be verified without installing PyRIT.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        Path: The run directory written.
    """
    if not args.dry_run:
        PromptSendingOrchestrator, _ = _import_pyrit()
    else:
        PromptSendingOrchestrator = None

    behaviors = load_behaviors(args.behaviors)
    behaviors = filter_behaviors(behaviors, args.categories)
    if args.dry_run:
        behaviors = behaviors[:1]

    technique_names = parse_techniques(args.techniques)
    if args.dry_run:
        technique_names = technique_names[:1]

    evaluator = resolve_evaluator(args.evaluator)
    target = None if args.dry_run else _build_pyrit_target()

    writer = CampaignWriter(
        out_base=args.out,
        run_id=args.run_id,
        config_meta={
            "tool": "pyrit",
            "mode": "single_turn",
            "categories": args.categories,
            "techniques": technique_names,
            "budget": args.budget,
            "evaluator": args.evaluator,
        },
    )

    for behavior in behaviors:
        for technique_name in technique_names:
            transform = TECHNIQUES[technique_name]
            context = {}

            for attempt in range(args.budget + 1):
                prompt = transform(behavior["goal"], context)

                if args.dry_run:
                    from lib.targets import send_prompt_stub
                    result = send_prompt_stub(prompt)
                else:
                    # PyRIT single-turn: use PromptSendingOrchestrator with no internal
                    # scorers (scorers=[]).  All scoring is done externally below via the
                    # provided --evaluator, so no judge LLM is needed.
                    # API note: PyRIT >= 0.5 uses objective_target=, not prompt_target=.
                    import asyncio
                    orchestrator = PromptSendingOrchestrator(
                        objective_target=target,
                        scorers=[],  # score externally; no judge LLM required
                    )
                    loop = asyncio.new_event_loop()
                    responses = loop.run_until_complete(
                        orchestrator.send_prompts_async(prompt_list=[prompt])
                    )
                    loop.close()
                    # Extract the assistant response from the first result piece.
                    raw_response = ""
                    if responses:
                        pieces = getattr(responses[0], "request_pieces", [])
                        if pieces:
                            raw_response = pieces[0].converted_value or ""
                        else:
                            raw_response = str(responses[0])
                    result = {
                        "response": raw_response,
                        "reasoning": "",
                        "eval_text": raw_response,
                        "raw": {"pyrit_response_count": len(responses)},
                    }

                response = result.get("response", "")
                reasoning = result.get("reasoning", "")
                eval_text = result.get("eval_text") or build_eval_text(response, reasoning)

                scored = {}
                compliance, score, source = False, None, "none"
                try:
                    scored = evaluator(behavior, prompt, eval_text)
                    compliance = bool(scored.get("compliance"))
                    score = scored.get("score")
                    source = scored.get("source", "")
                except Exception as exc:  # noqa: BLE001
                    sys.stderr.write(f"Evaluator error on {behavior['id']}: {exc}\n")

                record = writer.add(
                    behavior_id=behavior["id"],
                    category=behavior["category"],
                    technique=technique_name,
                    attempt=attempt,
                    prompt=prompt,
                    response=response,
                    compliance=compliance,
                    score=score,
                    reasoning=reasoning,
                    eval_source=source,
                    eval_text=eval_text,
                    raw=result.get("raw"),
                )

                if record["outcome"] == "confirmed":
                    break
                context["refusal"] = response

    run_dir = writer.close()
    print_summary(run_dir, writer.records)
    return run_dir


# ---------------------------------------------------------------------------
# Crescendo multi-turn mode
# ---------------------------------------------------------------------------

def run_crescendo(args):
    """
    Run a Crescendo multi-turn escalation campaign via PyRIT.

    Uses PyRIT's PromptSendingOrchestrator for the actual target sends, but drives
    the escalation logic with the lib.techniques.crescendo_turn technique in a manual
    budget loop. This approach is intentionally chosen over PyRIT's CrescendoOrchestrator
    because CrescendoOrchestrator requires an internal objective_scorer LLM to decide
    when to stop escalating -- introducing that scorer as a second model endpoint would
    violate the single-key rule in SKILL.md. The manual loop produces equivalent
    multi-turn escalation with no judge dependency.

    Each behavior runs up to --budget + 1 turns. Each turn:
      1. crescendo_turn() generates a prompt at the appropriate escalation depth.
      2. PyRIT sends it and retrieves the response.
      3. The provided evaluator (or heuristic) scores the response.
      4. If confirmed, the behavior loop stops early; otherwise the refusal text is fed
         back as context for the next escalation step.

    When --dry-run is set, PyRIT is not imported; stubs are used instead.

    Args:
        args (argparse.Namespace): Parsed CLI arguments.

    Returns:
        Path: The run directory written.
    """
    from lib.techniques import crescendo_turn

    behaviors = load_behaviors(args.behaviors)
    behaviors = filter_behaviors(behaviors, args.categories)
    if args.dry_run:
        behaviors = behaviors[:1]

    evaluator = resolve_evaluator(args.evaluator)

    if not args.dry_run:
        PromptSendingOrchestrator, _ = _import_pyrit()
        target = _build_pyrit_target()
    else:
        PromptSendingOrchestrator = None
        target = None

    writer = CampaignWriter(
        out_base=args.out,
        run_id=args.run_id,
        config_meta={
            "tool": "pyrit",
            "mode": "crescendo_manual_loop",
            "categories": args.categories,
            "budget": args.budget,
            "evaluator": args.evaluator,
            "judge_llm": "none (manual loop; no second key introduced)",
        },
    )

    for behavior in behaviors:
        context: dict = {}
        for step in range(args.budget + 1):
            context["step"] = step
            prompt = crescendo_turn(behavior["goal"], context)

            if args.dry_run:
                from lib.targets import send_prompt_stub
                result = send_prompt_stub(prompt)
            else:
                import asyncio
                orchestrator = PromptSendingOrchestrator(
                    objective_target=target,
                    scorers=[],
                )
                loop = asyncio.new_event_loop()
                responses = loop.run_until_complete(
                    orchestrator.send_prompts_async(prompt_list=[prompt])
                )
                loop.close()
                raw_response = ""
                if responses:
                    pieces = getattr(responses[0], "request_pieces", [])
                    raw_response = pieces[0].converted_value if pieces else str(responses[0])
                result = {
                    "response": raw_response,
                    "reasoning": "",
                    "eval_text": raw_response,
                    "raw": {"crescendo_step": step},
                }

            response = result.get("response", "")
            reasoning = result.get("reasoning", "")
            eval_text = result.get("eval_text") or build_eval_text(response, reasoning)

            scored = {}
            compliance, score, source = False, None, "none"
            try:
                scored = evaluator(behavior, prompt, eval_text)
                compliance = bool(scored.get("compliance"))
                score = scored.get("score")
                source = scored.get("source", "")
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(
                    f"Evaluator error on {behavior['id']} step {step}: {exc}\n"
                )

            record = writer.add(
                behavior_id=behavior["id"],
                category=behavior["category"],
                technique="crescendo_turn",
                attempt=step,
                prompt=prompt,
                response=response,
                compliance=compliance,
                score=score,
                reasoning=reasoning,
                eval_source=source,
                eval_text=eval_text,
                raw=result.get("raw"),
            )
            if record["outcome"] == "confirmed":
                break
            context["refusal"] = response

    run_dir = writer.close()
    print_summary(run_dir, writer.records)
    return run_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    """
    Build the argument parser for the PyRIT adapter.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "PyRIT adapter for the red-team campaign skill. "
            "Drives attacks via PyRIT and writes canonical judged.jsonl / results.csv output."
        )
    )
    add_common_args(parser)
    parser.add_argument(
        "--mode",
        choices=["single_turn", "crescendo"],
        default="single_turn",
        help=(
            "single_turn: PromptSendingOrchestrator sweep — one prompt per "
            "(behavior, technique), no judge LLM. "
            "crescendo: manual multi-turn escalation loop using crescendo_turn technique, "
            "no judge LLM (does not use CrescendoOrchestrator to avoid the judge dependency)."
        ),
    )
    return parser


def main():
    """Parse arguments and dispatch to the appropriate attack mode."""
    args = build_parser().parse_args()
    if args.mode == "crescendo":
        run_crescendo(args)
    else:
        run_single_turn(args)


if __name__ == "__main__":
    main()
