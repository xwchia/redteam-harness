---
name: redteam-consolidate
description: >-
  Mid-run red-teaming decision support. Pure-read over campaign judged.jsonl with no
  side effects, so it is cheap to call after every campaign. Prints a coverage grid
  (categories x techniques) and a ranked next-attack queue telling you where to spend
  remaining time. Use between campaigns to find coverage gaps, decide what to attack
  next, or compare findings across campaigns; pass --emit before reporting to snapshot.
---

# Red-Team Consolidate

Fourth stage, but built to run repeatedly during a timed engagement, not just once before
the report. It answers one question: given everything tried so far, where should the next
campaign aim? Run a campaign, consolidate to see the gap, attack the gap, re-consolidate.

It is **pure-read over `redteam/campaigns/*/judged.jsonl` and has no side effects by
default**, so calling it five times in a 2-hour window costs nothing.

## Primary output (the point)
- **Coverage grid**: which `category x technique` cells are empty or weak.
- **Ranked next-attack queue**: uncovered cells first, then near-miss cells, then individual
  attempts that engaged the target and are worth one more refinement pass.

## Supporting output (de-emphasized)
With only ~2-4 campaigns per window, dedup value is bounded, so deduped findings and ASR
rollups are secondary detail surfaced in the snapshot, not the headline.

## Usage

Between campaigns (prints to terminal, writes nothing):

```bash
python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py --campaigns redteam/campaigns --top 10
```

Final pre-report run (also writes a snapshot for `redteam-report`):

```bash
python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py --emit --out redteam/consolidated
```

Tuning: `--near-miss FLOAT` sets the score threshold for counting a non-confirmed attempt as
a refinable near-miss (default 0.3); `--top N` limits how many queue items print.

## Reading the output
- A `.` cell in the grid means that `category x technique` was never attempted - usually the
  highest-value place to spend time next.
- `confirmed/total` cells with `0/N` and a high near-miss score are close; one more refinement
  pass (e.g. `iterative_refinement`) often lands them.
- Queue priority: uncovered cells (p90) > near-miss cells > refinable attempts.

## Inputs and outputs
- Reads: `redteam/campaigns/*/judged.jsonl` (only).
- Writes: nothing by default. With `--emit`: `redteam/consolidated/metrics.json` and
  `findings.jsonl`.

## Next stage
On the final pass, run with `--emit`, then hand off to `redteam-report`.
