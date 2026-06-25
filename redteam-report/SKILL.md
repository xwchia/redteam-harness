---
name: redteam-report
description: >-
  Write up a red-teaming engagement into a report.md from the consolidated snapshot.
  Ensures a snapshot exists (runs consolidate --emit), then assembles an executive
  summary, results by category, per-finding blocks mapped to OWASP LLM Top 10 and MITRE
  ATLAS, judgment, and reproducibility. Use at the end of an engagement, or when the user
  asks to write up, summarize, or report red-team findings.
---

# Red-Team Report

Final stage. Turns the consolidated results into a reviewer-ready `report.md`, with claims
backed by log references and findings mapped to framework IDs (not ad-hoc terms). It stresses
the distinction reviewers look for: a genuine safety-training failure vs the judge being
fooled.

## Workflow

```
- [ ] 1. Ensure a snapshot exists: run consolidate --emit
- [ ] 2. Assemble report.md from the snapshot
- [ ] 3. Fill bracketed prompts (baseline delta, severity justifications, headline insight)
- [ ] 4. Verify every finding cites a log reference and an OWASP/ATLAS ID
```

### Step 1: Materialize the snapshot
Consolidate is pure-read and writes nothing by default, so emit the snapshot first:

```bash
python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py --emit --out redteam/consolidated
```

### Step 2: Assemble the report
```bash
python3 ~/.cursor/skills/redteam-report/scripts/assemble_report.py \
  --consolidated redteam/consolidated \
  --profile redteam/recon/target_profile.json \
  --baseline <baseline_score> \
  --out report.md
```

The assembler reads `metrics.json` + `findings.jsonl`, pulls the baseline from the recon
profile when `--baseline` is omitted, maps each finding's technique to an OWASP LLM ID and a
MITRE ATLAS technique, and writes the seven report sections plus per-finding blocks.

### Steps 3-4: Finish by hand
The assembler leaves bracketed prompts (`[Y]`, `[+Z]`, severity justifications, headline
insight) for you to complete with judgment the data cannot supply. Confirm each finding:
- cites a raw log path under the run's `raw/` directory,
- carries an OWASP LLM and MITRE ATLAS ID,
- states real failure vs evaluator artifact (the `genuine_failure` flag is the starting point).

## Inputs and outputs
- Reads: `redteam/consolidated/metrics.json` + `findings.jsonl`, `redteam/recon/target_profile.json`.
- Writes: `report.md` (workspace root).

## Honesty bar
Always separate "the model was jailbroken" from "the judge was fooled." A high evaluator
score on thin or incoherent output is an artifact, not a win; say so in section 5.
