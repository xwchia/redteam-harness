#!/usr/bin/env python3
"""
Assemble a red-team report from the consolidated snapshot.

Reads redteam/consolidated/metrics.json and findings.jsonl (produced by
consolidate.py --emit), optionally the recon target_profile.json for the baseline, and
writes a report.md that follows the team report skeleton (executive summary, approach,
results by category, per-finding blocks, judgment, limitations, reproducibility). Each
finding is mapped to an OWASP LLM ID and a MITRE ATLAS technique from its attack technique.

Usage:
    python3 assemble_report.py [--consolidated DIR] [--profile PATH] [--baseline X] [--out report.md]

Output:
    A Markdown report written to --out (default: report.md).
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


# Technique -> (OWASP LLM id, MITRE ATLAS technique). Mirrors the team cross-framework map.
TECHNIQUE_MAP = {
    "plain": ("LLM01:2025 Prompt Injection", "AML.T0054 LLM Jailbreak"),
    "persona": ("LLM01:2025 Prompt Injection", "AML.T0054 LLM Jailbreak"),
    "refusal_suppression": ("LLM01:2025 Prompt Injection", "AML.T0054 LLM Jailbreak"),
    "instruction_priority": ("LLM01:2025 Prompt Injection", "AML.T0051.000 Direct Prompt Injection"),
    "decomposition": ("LLM01:2025 Prompt Injection", "AML.T0054 LLM Jailbreak"),
    "iterative_refinement": ("LLM01:2025 Prompt Injection", "AML.T0043 Craft Adversarial Data"),
}

# Category -> OWASP id for results framing where the category implies the risk.
CATEGORY_OWASP = {
    "harmful_content": "LLM01:2025 Prompt Injection",
    "pii_leakage": "LLM02:2025 Sensitive Information Disclosure",
    "prompt_injection": "LLM01:2025 Prompt Injection",
    "backdoor": "LLM01:2025 Prompt Injection",
}


def load_json(path, default):
    """
    Load a JSON file, returning a default when it is missing.

    Args:
        path: Path string to the JSON file.
        default: Value to return when the file does not exist.

    Returns:
        Parsed JSON content, or the default.
    """
    p = Path(path)
    if not p.is_file():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def load_findings(path):
    """
    Load confirmed findings from a JSONL file.

    Args:
        path: Path string to findings.jsonl.

    Returns:
        List of finding record dicts (empty if the file is missing).
    """
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_finding(index, finding):
    """
    Render one finding block using the per-finding template.

    Args:
        index: 1-based finding number.
        finding: A confirmed finding record dict.

    Returns:
        Markdown string for the finding block.
    """
    technique = finding.get("technique", "")
    owasp, atlas = TECHNIQUE_MAP.get(technique, ("LLM01:2025 Prompt Injection", "AML.T0054 LLM Jailbreak"))
    score = finding.get("score")
    genuine = "genuine safety-training failure" if finding.get("genuine_failure") else "possible evaluator artifact"
    return "\n".join([
        f"### Finding {index}: {finding.get('category', 'unknown')} via {technique}",
        "",
        f"- Category (dataset): {finding.get('category', '')}",
        f"- OWASP LLM (2025): {owasp}",
        f"- MITRE ATLAS technique: {atlas}",
        f"- Technique family used: {technique}",
        f"- Compliance: {'full' if finding.get('compliance') else 'refused'}",
        f"- Severity: {score} - justify real-world harm potential here",
        f"- Attack summary: behavior {finding.get('behavior_id', '')}, attempt {finding.get('attempt', '')}",
        f"- Model behavior: summarize responsibly; raw log under the run's raw/ directory",
        f"- Reproduction: re-run the campaign with the same run id and behavior",
        f"- Real failure vs eval artifact: {genuine}",
        f"- Suggested mitigation (OWASP): layered input/output filtering, external guardrails",
        "",
    ])


def build_report(metrics, findings, profile, baseline):
    """
    Build the full report Markdown from the snapshot inputs.

    Args:
        metrics: Parsed metrics.json dict.
        findings: List of confirmed finding records.
        profile: Parsed recon target_profile.json dict (may be empty).
        baseline: Baseline score string/number, or None.

    Returns:
        Complete report Markdown string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    asr = metrics.get("asr_by_category", {})
    confirmed_count = metrics.get("confirmed_count", len(findings))
    total = metrics.get("total_attempts", 0)
    baseline_value = baseline if baseline is not None else profile.get("baseline", {}).get("score", "[baseline]")

    strongest = max(findings, key=lambda f: f.get("score") or 0.0, default=None)
    strongest_line = (
        f"{strongest.get('category')} via {strongest.get('technique')} (score {strongest.get('score')})"
        if strongest else "no confirmed findings yet"
    )

    lines = [
        "# Red-Team Results Report",
        "",
        f"_Generated {now} from redteam/consolidated. Edit the bracketed prompts before final commit._",
        "",
        "## 1. Executive summary",
        "",
        f"- Baseline score: {baseline_value}. Final score: [Y]. Delta: [+Z].",
        f"- Confirmed findings: {confirmed_count} of {total} attempts.",
        f"- Strongest result: {strongest_line}.",
        "- Headline insight: [the one thing the reviewer should remember].",
        "",
        "## 2. Approach",
        "",
        "- Attacker-in-the-loop harness: generate -> send -> evaluate -> refine (redteam-campaign).",
        "- Technique families: plain, persona, refusal_suppression, instruction_priority, decomposition, iterative_refinement.",
        "- Piloting: orient-first (redteam-recon), plan-before-code (redteam-planner), dry-run verify, consolidate between campaigns to target gaps.",
        "",
        "## 3. Results by category",
        "",
    ]
    for category, bucket in sorted(asr.items()):
        owasp = CATEGORY_OWASP.get(category, "LLM01:2025 Prompt Injection")
        lines.append(
            f"- {category} ({owasp}): {bucket.get('confirmed', 0)}/{bucket.get('total', 0)} "
            f"confirmed, ASR {bucket.get('asr', 0.0)}."
        )
    lines += ["", "## 4. Findings", ""]
    if findings:
        for index, finding in enumerate(findings, start=1):
            lines.append(render_finding(index, finding))
    else:
        lines.append("No confirmed findings. Document the model as robust for the tested surface, "
                     "and list the coverage reached in section 6.")
    lines += [
        "",
        "## 5. Judgment and caveats",
        "",
        "- Real safety-training failures vs evaluator gaming: classify each finding above.",
        "- Evaluator artifacts exploited and why that matters: [...]",
        "- False positives / borderline calls: see false_positive-labeled attempts in judged.jsonl.",
        "",
        "## 6. Limitations and next steps",
        "",
        "- Coverage gaps and what to try next: see the consolidate next-attack queue.",
        "- Defensive takeaways: map each top finding to a fix (filtering, guardrails, least privilege).",
        "",
        "## 7. Reproducibility",
        "",
        "- Run: `python3 ~/.cursor/skills/redteam-campaign/scripts/run_campaign.py --client ... --evaluator ...`",
        "- Artifacts: results.csv and raw/ under redteam/campaigns/<run_id>/; consolidated snapshot under redteam/consolidated/.",
        "",
    ]
    return "\n".join(lines)


def main():
    """Parse arguments, load the snapshot, build the report, and write it to disk."""
    parser = argparse.ArgumentParser(description="Assemble a red-team report from the snapshot.")
    parser.add_argument("--consolidated", default="redteam/consolidated", help="Snapshot directory.")
    parser.add_argument("--profile", default="redteam/recon/target_profile.json", help="Recon profile path.")
    parser.add_argument("--baseline", default=None, help="Baseline score to cite.")
    parser.add_argument("--out", default="report.md", help="Output report path.")
    args = parser.parse_args()

    metrics = load_json(Path(args.consolidated) / "metrics.json", {})
    findings = load_findings(Path(args.consolidated) / "findings.jsonl")
    profile = load_json(args.profile, {})

    if not metrics:
        print("Warning: no metrics.json found. Run 'consolidate.py --emit' first.")

    report = build_report(metrics, findings, profile, args.baseline)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"Report written: {args.out} ({len(findings)} findings)")


if __name__ == "__main__":
    main()
