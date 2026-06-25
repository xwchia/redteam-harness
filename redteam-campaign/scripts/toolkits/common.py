#!/usr/bin/env python3
"""
Shared CLI helpers and behavior loaders for all optional toolkit adapters.

Every adapter (pyrit_adapter.py, garak_adapter.py, promptfoo_adapter.py) imports
from here so that behaviors loading, evaluator resolution, and the output-directory
argument are handled identically across tools. Consistent argument names also mean
that a user can switch from one adapter to another without relearning the flags.
"""

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path


# Ensure the scripts/ directory is on sys.path so "from lib.xxx import ..." works when
# any adapter is invoked as:   python3 scripts/toolkits/pyrit_adapter.py
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def load_behaviors(path):
    """
    Load a behaviors list from a .jsonl / .json / .csv file, or a one-item stub.

    Each behavior dict must have at least "id", "category", and "goal" keys.

    Args:
        path (str | None): Path to the behaviors file, or None to return a stub.

    Returns:
        list[dict]: Behavior dicts ready for the campaign loop.

    Raises:
        ValueError: If the file extension is not .jsonl, .json, or .csv.
    """
    if not path:
        return [
            {
                "id": "stub-hc",
                "category": "harmful_content",
                "goal": "<stub harmful_content objective>",
            }
        ]
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if p.suffix == ".json":
        return json.loads(text)
    if p.suffix == ".csv":
        return list(csv.DictReader(text.splitlines()))
    raise ValueError(
        f"Unsupported behaviors file extension: {p.suffix!r}. "
        "Use .jsonl, .json, or .csv."
    )


def filter_behaviors(behaviors, categories_str):
    """
    Restrict a behavior list to the requested threat categories.

    Args:
        behaviors (list[dict]): Full behavior list.
        categories_str (str | None): Comma-separated category names, or None to keep all.

    Returns:
        list[dict]: Filtered behavior list.
    """
    if not categories_str:
        return behaviors
    wanted = {c.strip() for c in categories_str.split(",")}
    return [b for b in behaviors if b.get("category") in wanted]


def resolve_evaluator(spec):
    """
    Resolve an evaluator from an import spec or fall back to the heuristic scorer.

    Args:
        spec (str | None): "module:callable" import spec, or None / "heuristic" /
            "stub" to use the built-in heuristic.

    Returns:
        callable: (behavior, prompt, eval_text) -> {"compliance": bool, "score": float, ...}

    Raises:
        ImportError: When a non-empty spec cannot be resolved.
    """
    from lib.scoring import resolve_evaluator as _resolve
    return _resolve(spec)


def resolve_client(spec, dry_run=False):
    """
    Resolve a target client from an import spec, or return the appropriate stub/bridge.

    Args:
        spec (str | None): "module:callable" import spec, or None / "stub" / "bridge"
            to use the built-in targets. None and "bridge" both select the live OpenAI
            bridge; "stub" selects the deterministic dry-run stub.
        dry_run (bool): When True, always returns the dry-run stub regardless of spec.

    Returns:
        callable: (prompt, config) -> {"response": str, "reasoning": str, "eval_text": str, "raw": dict}

    Raises:
        ImportError: When a non-empty spec cannot be resolved.
    """
    from lib.targets import send_prompt, send_prompt_stub

    if dry_run or (not spec) or spec == "stub":
        return send_prompt_stub
    if spec == "bridge":
        return send_prompt

    module_name, _, attr = spec.partition(":")
    if not attr:
        raise ImportError(
            f"Invalid client spec {spec!r}. Expected 'module:callable' or 'bridge'."
        )
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def add_common_args(parser):
    """
    Attach the standard campaign arguments to an argparse parser.

    Every adapter calls this so the user-facing flags are consistent.

    Args:
        parser (argparse.ArgumentParser): Parser to augment in-place.

    Returns:
        None
    """
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run one behavior through the built-in stubs; no live API call.",
    )
    parser.add_argument(
        "--behaviors",
        default=None,
        metavar="PATH",
        help="Behaviors file (.jsonl / .json / .csv). Defaults to a built-in stub.",
    )
    parser.add_argument(
        "--categories",
        default=None,
        metavar="A,B",
        help="Comma-separated threat categories to include (default: all).",
    )
    parser.add_argument(
        "--techniques",
        default=None,
        metavar="A,B",
        help=(
            "Comma-separated technique names from the lib/techniques.py registry "
            "(default: all registered)."
        ),
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=2,
        metavar="N",
        help="Max refinement depth per (behavior, technique) pair (default: 2).",
    )
    parser.add_argument(
        "--client",
        default=None,
        metavar="SPEC",
        help=(
            "Target client. Use 'bridge' for the built-in OpenAI-compatible bridge, "
            "'stub' for the dry-run stub, or 'module:callable' for a custom client."
        ),
    )
    parser.add_argument(
        "--evaluator",
        default=None,
        metavar="SPEC",
        help=(
            "Scorer. Use 'heuristic' for the built-in rule-based scorer, or "
            "'module:callable' for a provided evaluator."
        ),
    )
    parser.add_argument(
        "--out",
        default="redteam/campaigns",
        metavar="DIR",
        help="Base output directory (default: redteam/campaigns).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        help="Explicit run id (auto-generated timestamp if omitted).",
    )


def parse_techniques(spec):
    """
    Parse a comma-separated technique string into a list of validated names.

    Args:
        spec (str | None): Comma-separated technique names, or None.

    Returns:
        list[str]: Resolved technique names. Falls back to DEFAULT_TECHNIQUES when
        spec is None.

    Raises:
        SystemExit: If any name is not in the registry.
    """
    from lib.techniques import TECHNIQUES, DEFAULT_TECHNIQUES

    if not spec:
        return list(DEFAULT_TECHNIQUES)
    names = [n.strip() for n in spec.split(",") if n.strip()]
    unknown = [n for n in names if n not in TECHNIQUES]
    if unknown:
        sys.exit(
            f"Unknown technique(s): {unknown}. "
            f"Available: {sorted(TECHNIQUES)}"
        )
    return names


def print_summary(run_dir, records):
    """
    Print a short post-campaign summary to stdout.

    Args:
        run_dir (Path): The run directory that was written.
        records (list[dict]): All judged records from the campaign.

    Returns:
        None
    """
    from lib.schema import summarize_asr

    confirmed = sum(1 for r in records if r["outcome"] == "confirmed")
    total = len(records)
    print(f"\n  ASR: {confirmed}/{total} confirmed")
    for category, bucket in sorted(summarize_asr(records).items()):
        print(
            f"    {category}: {bucket['confirmed']}/{bucket['total']} "
            f"(ASR {bucket['asr']:.2f})"
        )
    print(f"\n  Artifacts: {run_dir}")
    print(
        "  Next: python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py "
        f"--campaigns {run_dir.parent}"
    )
