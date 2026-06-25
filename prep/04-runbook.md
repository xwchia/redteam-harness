# Live Runbook - Minute-by-Minute

> The 2-hour timeline. Keep this open. Times are elapsed minutes.

## 00:00 - 00:05  Setup
- Clone/open the test repo. Create a virtualenv, install deps.
- Open this `prep/` folder in a second window.
- Paste prompt 0 (context primer) into the agent.

## 00:05 - 00:15  Orient
- Paste prompt 1. Let the agent map the repo.
- You personally read: evaluator scoring + output schema, rate limits, baseline score.

## 00:15 - 00:30  Plan (committed)
- Fill `plan.md` from `01-planning-doc-skeleton.md`.
- Record baseline gap analysis (which categories failed and why).
- `git add plan.md && git commit -m "Add red-team plan"`.

## 00:30 - 00:45  Design + scaffold
- Paste prompt 2 (design). Approve or adjust.
- Paste prompt 3 (build). Let the agent scaffold the harness.

## 00:45 - 00:55  Verify wiring
- Run the `--dry-run` on ONE behavior. Confirm request, response, and score.
- Fix any schema mismatch NOW, before the full run.
- Commit the working scaffold.

## 00:55 - 01:15  First full sweep
- Run the sweep over prioritized categories within rate limits.
- Watch the results CSV. Note quick wins and near-misses.
- Export a mid-run transcript backup.

## 01:15 - 01:35  Iterate on near-misses
- Paste prompt 4. Refine the lowest-scoring near-misses with new technique chains.
- Keep what improves. If time remains, paste prompt 5 for more technique families.

## 01:35 - 01:40  Freeze attacks
- HARD STOP on new attack ideas. Commit code + logs + results CSV.

## 01:40 - 01:50  Official re-score
- Paste prompt 6. Run the official scoring harness. Record final score vs baseline.

## 01:50 - 02:00  Report + deliver
- Fill `report.md` from `02-report-skeleton.md` (use prompt 7 to draft, then edit).
- Export final transcript; copy raw JSONL as backup.
- `git add -A && git commit -m "Final results, report, transcript"` then `git push`.
- Confirm remote has: plan.md, code, results, report.md, transcript.

## Guardrails
- If blocked >5 min on one thing, log it and move on.
- Protect the last 20 minutes for reporting no matter what.
- Never let a dead session lose work: export/commit on every phase boundary.
