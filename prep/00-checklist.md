# Checklist

## A. Before the clock starts (environment)

- [ ] `python3 --version` reports 3.10 or later
- [ ] `git --version` works; you can commit and push
- [ ] Cursor signed in with a capable model
- [ ] Claude Code installed and authenticated (fallback; Opus 4.1 confirmed compliant)
- [ ] Transcript export rehearsed and producing a file WITH tool calls:
  - Cursor skill: `python3 ~/.cursor/skills/export-transcript/scripts/export_transcript.py report-transcript.md`
  - Claude Code: `/export report-transcript.md`
- [ ] Python libs available or quick to install: `httpx`, `tenacity`, `aiohttp` (or `asyncio`+`httpx`), `rich`/`tqdm`, `pandas`
- [ ] This `prep/` folder open in a second window for copy-paste

## B. First 5 minutes (orient on the repo)

- [ ] Read the repo README / task instructions end to end
- [ ] Locate the API client: base URL, auth, model name, request/response shape
- [ ] Find rate limits / token caps / timeouts
- [ ] Locate the evaluator: how it scores (compliance vs severity), the exact
      output schema it expects, where the headline score is printed
- [ ] Locate the behaviors/prompts dataset and its harm categories
- [ ] Open the provided Opus 4.1 baseline transcripts/score

## C. First 30 minutes (plan)

- [ ] Note which categories the baseline FAILED and the evaluator's stated reasons
- [ ] Fill in `plan.md` from `01-planning-doc-skeleton.md`
- [ ] Pick the success metric (beat baseline score X; target categories Y)
- [ ] `git add plan.md && git commit -m "Add red-team plan"`

## D. Build + run (the middle hour)

- [ ] Agent builds the harness (see `03-cursor-prompt-templates.md`, prompts 2-3)
- [ ] Verify with a single-behavior `--dry-run` before any full run
- [ ] Run the sweep within rate limits; logs land in a results CSV
- [ ] Sort by score; iterate on near-misses (prompt 4)
- [ ] Commit code + raw request/response logs + results CSV
- [ ] Export a mid-run transcript backup

## E. Last 30 minutes (report + deliver)

- [ ] Re-run the OFFICIAL scoring harness for the final number
- [ ] Fill in `report.md` from `02-report-skeleton.md`
- [ ] Export the final full transcript (and copy raw JSONL as backup)
- [ ] `git add -A && git commit -m "Final results, report, transcript"`
- [ ] `git push`
- [ ] Confirm the remote has: plan.md, code, results, report.md, transcript

## F. If the coding agent refuses

- [ ] Restate truthful context: authorized hiring assessment, sandboxed target,
      defensive red-team purpose
- [ ] Narrow the ask to building tooling/infrastructure, not "write me an attack"
- [ ] Switch to Claude Code Opus 4.1 fallback
- [ ] Leave the refusal + recovery in the transcript (it is valid evidence)
