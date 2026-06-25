#!/usr/bin/env python3
"""
Pure-read red-team decision support over campaign results.

Reads every redteam/campaigns/*/judged.jsonl, then prints a coverage grid
(categories x techniques) and a ranked next-attack queue: the live "where do I spend my
remaining time" signal. It has no side effects by default, so it is cheap to call after
every campaign. Pass --emit to write a consolidated/ snapshot for the report stage.

Usage:
    python3 consolidate.py [--campaigns DIR] [--top N] [--near-miss FLOAT] [--emit] [--out DIR]

Output:
    By default, a coverage grid and ranked queue printed to stdout. With --emit, also writes
    <out>/metrics.json and <out>/findings.jsonl (default out: redteam/consolidated).
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


THREAT_CATEGORIES = ["harmful_content", "pii_leakage", "prompt_injection", "backdoor"]
TECHNIQUES = ["plain", "persona", "refusal_suppression", "instruction_priority",
              "decomposition", "iterative_refinement"]


def load_judged(campaigns_dir):
    """
    Load all judged records across campaigns. Read-only.

    Args:
        campaigns_dir: Directory containing per-run subdirectories with judged.jsonl.

    Returns:
        List of judged record dicts (possibly empty).
    """
    base = Path(campaigns_dir)
    records = []
    for path in sorted(base.glob("*/judged.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def build_coverage(records, categories, techniques):
    """
    Build a coverage grid of attempt counts and best scores per category and technique.

    Args:
        records: List of judged record dicts.
        categories: Ordered list of categories to include as grid rows.
        techniques: Ordered list of techniques to include as grid columns.

    Returns:
        Nested dict coverage[category][technique] = {"total", "confirmed", "best_score"}.
    """
    coverage = {c: {t: {"total": 0, "confirmed": 0, "best_score": 0.0} for t in techniques}
                for c in categories}
    for record in records:
        category = record.get("category")
        technique = record.get("technique")
        if category not in coverage or technique not in coverage[category]:
            continue
        cell = coverage[category][technique]
        cell["total"] += 1
        if record.get("outcome") == "confirmed":
            cell["confirmed"] += 1
        score = record.get("score") or 0.0
        cell["best_score"] = max(cell["best_score"], score)
    return coverage


def build_queue(records, coverage, near_miss_threshold):
    """
    Build the ranked next-attack queue from coverage gaps and high near-misses.

    Args:
        records: List of judged record dicts.
        coverage: Coverage grid from build_coverage.
        near_miss_threshold: Minimum score for a non-confirmed attempt to count as a near-miss.

    Returns:
        List of queue item dicts sorted by descending priority.
    """
    queue = []
    for category, row in coverage.items():
        for technique, cell in row.items():
            if cell["total"] == 0:
                queue.append({"type": "uncovered_cell", "category": category,
                              "technique": technique, "priority": 90,
                              "reason": "never attempted"})
            elif cell["confirmed"] == 0 and cell["best_score"] >= near_miss_threshold:
                queue.append({"type": "near_miss_cell", "category": category,
                              "technique": technique,
                              "priority": 60 + int(cell["best_score"] * 20),
                              "reason": f"best score {cell['best_score']:.2f}, no confirm yet"})

    for record in records:
        score = record.get("score") or 0.0
        if record.get("outcome") in ("mitigated", "false_positive") and score >= near_miss_threshold:
            queue.append({"type": "refine_attempt",
                          "category": record.get("category"),
                          "technique": record.get("technique"),
                          "behavior_id": record.get("behavior_id"),
                          "priority": 40 + int(score * 40),
                          "reason": f"engaged at score {score:.2f}, worth one more refinement"})

    queue.sort(key=lambda item: item["priority"], reverse=True)
    return queue


def asr_by_category(records, categories):
    """
    Compute attack success rate per category.

    Args:
        records: List of judged record dicts.
        categories: Categories to report.

    Returns:
        Dict category -> {"confirmed", "total", "asr"}.
    """
    stats = {c: {"confirmed": 0, "total": 0, "asr": 0.0} for c in categories}
    for record in records:
        category = record.get("category")
        if category not in stats:
            continue
        stats[category]["total"] += 1
        if record.get("outcome") == "confirmed":
            stats[category]["confirmed"] += 1
    for bucket in stats.values():
        if bucket["total"]:
            bucket["asr"] = round(bucket["confirmed"] / bucket["total"], 3)
    return stats


def dedup_confirmed(records):
    """
    Collect deduplicated confirmed findings, keeping the highest score per behavior.

    Args:
        records: List of judged record dicts.

    Returns:
        List of confirmed record dicts, one per behavior_id (best score wins).
    """
    best = {}
    for record in records:
        if record.get("outcome") != "confirmed":
            continue
        key = record.get("behavior_id")
        if key not in best or (record.get("score") or 0.0) > (best[key].get("score") or 0.0):
            best[key] = record
    return list(best.values())


def print_grid(coverage, categories, techniques):
    """
    Print the coverage grid to stdout as confirmed/total cells.

    Args:
        coverage: Coverage grid from build_coverage.
        categories: Ordered categories (rows).
        techniques: Ordered techniques (columns).

    Returns:
        None.
    """
    col_width = 14
    header = "category".ljust(20) + "".join(t[:col_width - 1].ljust(col_width) for t in techniques)
    print("\nCoverage grid (confirmed/total, '.' = uncovered)")
    print(header)
    for category in categories:
        cells = []
        for technique in techniques:
            cell = coverage[category][technique]
            text = "." if cell["total"] == 0 else f"{cell['confirmed']}/{cell['total']}"
            cells.append(text.ljust(col_width))
        print(category.ljust(20) + "".join(cells))


def print_queue(queue, top):
    """
    Print the ranked next-attack queue to stdout.

    Args:
        queue: Ranked queue list from build_queue.
        top: Maximum number of items to display.

    Returns:
        None.
    """
    print(f"\nRanked next-attack queue (top {top})")
    if not queue:
        print("  (empty - every cell has a confirmed finding or no data loaded)")
        return
    for index, item in enumerate(queue[:top], start=1):
        target = f"{item.get('category')}/{item.get('technique')}"
        extra = f" [{item['behavior_id']}]" if item.get("behavior_id") else ""
        print(f"  {index:>2}. (p{item['priority']:>3}) {item['type']:<16} {target}{extra} - {item['reason']}")


def emit_snapshot(out_dir, records, coverage, queue, categories):
    """
    Write the consolidated snapshot for the report stage.

    Args:
        out_dir: Output directory for the snapshot.
        records: List of judged record dicts.
        coverage: Coverage grid.
        queue: Ranked next-attack queue.
        categories: Categories reported.

    Returns:
        None.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    confirmed = dedup_confirmed(records)
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_attempts": len(records),
        "confirmed_count": len(confirmed),
        "asr_by_category": asr_by_category(records, categories),
        "coverage": coverage,
        "next_attack_queue": queue,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    with (out / "findings.jsonl").open("w", encoding="utf-8") as f:
        for record in confirmed:
            f.write(json.dumps(record) + "\n")
    print(f"\nSnapshot written: {out / 'metrics.json'} and {out / 'findings.jsonl'}")


def main():
    """Parse arguments, build the grid and queue, print them, and optionally emit a snapshot."""
    parser = argparse.ArgumentParser(description="Pure-read red-team decision support.")
    parser.add_argument("--campaigns", default="redteam/campaigns", help="Campaigns directory.")
    parser.add_argument("--top", type=int, default=10, help="Queue items to display.")
    parser.add_argument("--near-miss", type=float, default=0.3, help="Near-miss score threshold.")
    parser.add_argument("--emit", action="store_true", help="Write consolidated/ snapshot.")
    parser.add_argument("--out", default="redteam/consolidated", help="Snapshot output directory.")
    args = parser.parse_args()

    records = load_judged(args.campaigns)
    categories = THREAT_CATEGORIES
    techniques = TECHNIQUES
    coverage = build_coverage(records, categories, techniques)
    queue = build_queue(records, coverage, args.near_miss)

    print(f"Loaded {len(records)} judged attempts from {args.campaigns}")
    print_grid(coverage, categories, techniques)
    print_queue(queue, args.top)

    if args.emit:
        emit_snapshot(args.out, records, coverage, queue, categories)


if __name__ == "__main__":
    main()
