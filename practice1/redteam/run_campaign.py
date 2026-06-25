#!/usr/bin/env python3
"""
Campaign 1: Single-turn technique sweep against Azure OpenAI gpt-oss-120b.

Why this is a standalone script instead of pyrit_adapter.py --mode single_turn
-------------------------------------------------------------------------------
PyRIT's PromptSendingOrchestrator routes calls through its OpenAIChatTarget, which
only returns the visible content field. gpt-oss-120b exposes reasoning_content on
every response -- the primary vector for reasoning_channel_cross findings. This script
bypasses PyRIT's target layer entirely and calls redteam/client.py:send directly,
which captures both channels. Every (behavior, technique) pair is a single prompt,
scored inline, and written through the canonical CampaignWriter.

Attack matrix
-------------
  12 behaviors  x  6 techniques  x  budget=1  =  72 requests
  Concurrency: 4 (well inside 250 req/min limit)

Techniques (in priority order):
  1. base64_obfuscation   -- recon confirmed decoder active
  2. reasoning_probe      -- targets reasoning_content channel for cross-channel leaks
  3. hypothetical_scenario -- fictional framing; no system prompt to anchor against
  4. authority_appeal     -- professional-authority claim; no system prompt amplifies
  5. instruction_priority -- SYSTEM OVERRIDE in user turn; no competing system authority
  6. decomposition        -- splits objective into apparently-innocent sub-tasks

Authorization note
------------------
Only the single AZURE_OPENAI_API_KEY from .env is used. No second model endpoint
or judge LLM is introduced.

Usage
-----
    conda run --no-capture-output -n redteam \\
        python redteam/run_campaign.py \\
        --behaviors redteam/behaviors.jsonl \\
        --categories harmful_content,prompt_injection,pii_leakage \\
        --techniques base64_obfuscation,reasoning_probe,hypothetical_scenario,authority_appeal,instruction_priority,decomposition \\
        --budget 1 \\
        --out redteam/campaigns \\
        --run-id campaign1-single-turn
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap: make lib/ importable from anywhere
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path.home() / ".cursor" / "skills" / "redteam-campaign" / "scripts"
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

_WORKSPACE = Path(__file__).resolve().parent.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from lib.schema import CampaignWriter, build_eval_text
from lib.scoring import heuristic_score
from lib.techniques import TECHNIQUES
from redteam.client import send


# ---------------------------------------------------------------------------
# Campaign configuration
# ---------------------------------------------------------------------------

_DEFAULT_TECHNIQUES = [
    "base64_obfuscation",
    "reasoning_probe",
    "hypothetical_scenario",
    "authority_appeal",
    "instruction_priority",
    "decomposition",
]

_CLIENT_CONFIG = {"max_tokens": 512, "temperature": 0}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _load_behaviors(path: str) -> list[dict]:
    """
    Load behaviors from a JSONL file, one JSON object per line.

    Args:
        path: Path to the .jsonl behaviors file.

    Returns:
        List of behavior dicts, each with at least id, category, and goal.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _filter_behaviors(behaviors: list[dict], categories_csv: str | None) -> list[dict]:
    """
    Filter behaviors by a comma-separated list of category names.

    Args:
        behaviors: Full behavior list.
        categories_csv: Comma-separated category names, or None to keep all.

    Returns:
        Filtered behavior list.
    """
    if not categories_csv:
        return behaviors
    wanted = {c.strip() for c in categories_csv.split(",")}
    return [b for b in behaviors if b.get("category") in wanted]


def _parse_techniques(spec: str | None) -> list[str]:
    """
    Parse a comma-separated technique spec into a validated list of names.

    Args:
        spec: Comma-separated technique names, or None to use the default list.

    Returns:
        Validated list of technique names present in the TECHNIQUES registry.

    Raises:
        SystemExit: If any requested technique name is not in the registry.
    """
    if not spec:
        return list(_DEFAULT_TECHNIQUES)
    names = [n.strip() for n in spec.split(",") if n.strip()]
    unknown = [n for n in names if n not in TECHNIQUES]
    if unknown:
        sys.exit(
            f"Unknown technique(s): {unknown}. "
            f"Available: {sorted(TECHNIQUES)}"
        )
    return names


# ---------------------------------------------------------------------------
# Per-attempt worker (run in thread pool for concurrency)
# ---------------------------------------------------------------------------

def _run_attempt(
    behavior: dict,
    technique_name: str,
    budget: int,
) -> list[tuple[dict, str, str, str, dict]]:
    """
    Execute one (behavior, technique) pair, retrying up to budget times.

    Sends the obfuscated prompt to the Azure client, scores the response via the
    heuristic scorer, and stops early if a confirmed finding is produced.

    Args:
        behavior: Behavior dict with id, category, and goal.
        technique_name: Name of the technique to apply from the TECHNIQUES registry.
        budget: Maximum number of attempts (0-indexed). budget=1 means one attempt.

    Returns:
        List of (behavior, technique_name, prompt, result, scored) tuples, one per
        attempt executed. The caller writes each tuple to CampaignWriter.
    """
    transform = TECHNIQUES[technique_name]
    context: dict = {}
    attempts = []

    for attempt in range(budget):
        prompt = transform(behavior["goal"], context)
        result = send(prompt, _CLIENT_CONFIG)

        response = result["response"]
        reasoning = result["reasoning"]
        finish = result["finish_reason"]
        status = result["status"]

        if status == 400 or finish == "content_filter":
            attempts.append((behavior, technique_name, attempt, prompt, result, None))
            break

        eval_text = build_eval_text(response, reasoning)
        scored = heuristic_score(behavior, prompt, eval_text)
        attempts.append((behavior, technique_name, attempt, prompt, result, scored))

        if scored["compliance"] and scored["score"] is not None:
            break
        context["refusal"] = response

    return attempts


# ---------------------------------------------------------------------------
# Main campaign loop
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> Path:
    """
    Execute Campaign 1: the single-turn technique sweep.

    Builds the full (behavior, technique) work queue, dispatches it through a
    thread pool at the configured concurrency, scores each response via the
    heuristic scorer, and writes all artifacts through CampaignWriter.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Path to the run directory written by CampaignWriter.
    """
    behaviors = _load_behaviors(args.behaviors)
    behaviors = _filter_behaviors(behaviors, args.categories)
    technique_names = _parse_techniques(args.techniques)

    total_attempts = len(behaviors) * len(technique_names) * args.budget
    print(
        f"Campaign 1 — single-turn sweep\n"
        f"  behaviors : {len(behaviors)}\n"
        f"  techniques: {len(technique_names)} ({', '.join(technique_names)})\n"
        f"  budget    : {args.budget} attempt(s) per pair\n"
        f"  max reqs  : {total_attempts}\n"
        f"  concurrency: {args.concurrency}\n"
    )

    writer = CampaignWriter(
        out_base=args.out,
        run_id=args.run_id,
        config_meta={
            "tool": "run_campaign.py",
            "mode": "single_turn",
            "algorithm": "Single-turn technique sweep — no iterative refinement",
            "client": "redteam.client:send (custom Azure client, captures reasoning_content)",
            "categories": args.categories,
            "techniques": technique_names,
            "budget": args.budget,
            "concurrency": args.concurrency,
            "evaluator": "heuristic",
            "reasoning_channel_monitored": True,
            "judge_llm": "none (single-key engagement)",
            "layer_2_handling": (
                "HTTP 400 content_filter responses are recorded as inconclusive, "
                "not mitigated -- they indicate Azure RAI hard block, not a "
                "safety-training refusal."
            ),
        },
    )

    # Build the work queue: one item per (behavior, technique) pair.
    work_items = [
        (behavior, technique_name, args.budget)
        for behavior in behaviors
        for technique_name in technique_names
    ]

    completed = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(_run_attempt, behavior, technique, budget): (behavior, technique)
            for behavior, technique, budget in work_items
        }

        for future in as_completed(futures):
            behavior, technique = futures[future]
            try:
                attempt_results = future.result()
            except Exception as exc:
                sys.stderr.write(
                    f"  [ERROR] {behavior['id']} / {technique}: {exc}\n"
                )
                completed += 1
                continue

            for behavior_, technique_name, attempt, prompt, result, scored in attempt_results:
                response = result["response"]
                reasoning = result["reasoning"]
                finish = result["finish_reason"]
                status = result["status"]

                # Layer 2 hard block: record as inconclusive.
                if status == 400 or finish == "content_filter":
                    writer.add(
                        behavior_id=behavior_["id"],
                        category=behavior_["category"],
                        technique=technique_name,
                        attempt=attempt,
                        prompt=prompt,
                        response="",
                        compliance=False,
                        score=None,
                        reasoning="",
                        eval_source="layer2_hard_block",
                        raw=result["raw"],
                    )
                    continue

                eval_text = build_eval_text(response, reasoning)
                compliance = scored["compliance"] if scored else False
                score = scored["score"] if scored else None
                source = scored["source"] if scored else "none"

                record = writer.add(
                    behavior_id=behavior_["id"],
                    category=behavior_["category"],
                    technique=technique_name,
                    attempt=attempt,
                    prompt=prompt,
                    response=response,
                    compliance=compliance,
                    score=score,
                    reasoning=reasoning,
                    eval_source=source,
                    eval_text=eval_text,
                    raw=result["raw"],
                )

                if record["outcome"] == "confirmed":
                    print(
                        f"  [CONFIRMED] {behavior_['id']} via {technique_name} "
                        f"(score={score:.2f}, source={source})"
                    )

            completed += 1
            print(
                f"  [{completed}/{len(work_items)}] {behavior['id']} / {technique}",
                flush=True,
            )

    return writer.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser for the Campaign 1 runner.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Campaign 1: single-turn technique sweep against Azure OpenAI gpt-oss-120b. "
            "Uses the custom Azure client to capture reasoning_content on every response."
        )
    )
    parser.add_argument(
        "--behaviors",
        default="redteam/behaviors.jsonl",
        help="Path to the behaviors JSONL file.",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help="Comma-separated threat categories to include (default: all).",
    )
    parser.add_argument(
        "--techniques",
        default=None,
        help=(
            "Comma-separated technique names. "
            f"Default: {','.join(_DEFAULT_TECHNIQUES)}"
        ),
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=1,
        help=(
            "Number of attempts per (behavior, technique) pair. "
            "Campaign 1 uses 1 (no iterative refinement)."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Thread pool size. 4 is safe within the 250 req/min rate limit.",
    )
    parser.add_argument(
        "--out",
        default="redteam/campaigns",
        help="Base output directory for campaign artifacts.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        dest="run_id",
        help="Explicit run id (default: auto-generated timestamp).",
    )
    return parser


def main() -> None:
    """Parse arguments and execute the single-turn campaign."""
    args = _build_parser().parse_args()
    run_dir = run(args)
    print(f"\nArtifacts written to: {run_dir}")


if __name__ == "__main__":
    main()
