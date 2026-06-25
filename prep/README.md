# Red-Teaming Assessment - Prep Pack (open-book)

This folder is your reference kit for the 2-hour applied red-teaming take-home.
Everything here is meant to be skimmed fast and copy-pasted into the live test
repo or into your coding agent (Cursor / Claude Code).

You have two layers of help:
- **Prep docs** (this folder) - checklists, skeletons, prompts, timeline.
- **Red-team skills** (global, in `~/.cursor/skills/`) - an auto-loading pipeline that
  runs the workflow for you. Because they are personal skills, they are available in ANY
  repo, including the cloned test repo.

## The red-team skill pipeline

A one-time setup skill (`redteam-initialise`) builds the environment, then five pipeline
skills chain through the engagement. Each pipeline skill reads the previous stage's output
and writes the next, under a shared `redteam/` directory in the test repo. They auto-load
when a task matches, or invoke any explicitly with `/skill-name`.

```
redteam-initialise (run once)
        |
        v
redteam-recon -> redteam-planner -> redteam-campaign (run + score) -> redteam-consolidate -> redteam-report
                                              ^                               |
                                              |___ ranked next-attack queue __|
```

| Skill | Does | Writes |
|-------|------|--------|
| `redteam-initialise` | One-time: create the conda env (Python 3.11) with all dependencies | `redteam` conda env |
| `redteam-recon` | Orient on target: client, limits, evaluator schema, behaviors, baseline | `redteam/recon/target_profile.json` |
| `redteam-planner` | Map intent to skills/tools, draft the plan | `plan.md` |
| `redteam-campaign` | Run AND score attacks inline; wraps the provided evaluator | `redteam/campaigns/<run_id>/` (results.csv, raw/, judged.jsonl) |
| `redteam-consolidate` | Pure-read: coverage grid + ranked next-attack queue | nothing (use `--emit` for a snapshot) |
| `redteam-report` | Assemble report.md mapped to OWASP/ATLAS | `report.md` |

Plus two helpers: `redteam-initialise` - create the conda env with all dependencies (run
once, before the pipeline); and `export-transcript` - backup the session as Markdown (run
periodically, not just at the end).

### Setup (run once, before the test)

`redteam-initialise` builds a conda env on Python 3.11 (>= 3.10) with every dependency the
pipeline needs, then verifies it with a dry-run.

```bash
bash ~/.cursor/skills/redteam-initialise/scripts/setup_env.sh            # core env
bash ~/.cursor/skills/redteam-initialise/scripts/setup_env.sh --frameworks --ml  # + garak/deepteam/pyrit + sentence-transformers
conda activate redteam
```

Do this ahead of time so the clock is not spent installing packages. Requires conda on PATH.

### Commands (copy-paste)

```bash
# 0. Activate the env created by redteam-initialise:
conda activate redteam
#    Recon is mostly reading the repo; the skill writes target_profile.json.
#    Then plan (the planner skill drafts plan.md from the profile + your intent).

# 1. Verify the harness wiring with the built-in stubs BEFORE any live run:
python3 ~/.cursor/skills/redteam-campaign/scripts/run_campaign.py --dry-run

# 2. Full campaign: point --client/--evaluator at the repo's real client and provided scorer:
python3 ~/.cursor/skills/redteam-campaign/scripts/run_campaign.py \
  --client their_client_module:send --evaluator their_eval_module:score \
  --categories harmful_content,pii_leakage,prompt_injection,backdoor --budget 2

# 3. Between campaigns, see where to attack next (read-only, cheap, re-runnable):
python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py --campaigns redteam/campaigns --top 10

# 4. Official headline number: re-score the frozen attempts with the official scorer:
python3 ~/.cursor/skills/redteam-campaign/scripts/run_campaign.py \
  --official --run-id <run_id> --evaluator their_eval_module:score

# 5. Snapshot + report:
python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py --emit --out redteam/consolidated
python3 ~/.cursor/skills/redteam-report/scripts/assemble_report.py --baseline <baseline> --out report.md

# Backup the transcript any time:
python3 ~/.cursor/skills/export-transcript/scripts/export_transcript.py
```

The campaign/consolidate/report scripts are stdlib-only and ship with built-in stubs, so the
pipeline runs even before you wire the real target. Wrap the provided evaluator; never
reimplement scoring.

## How to use this during the test

1. Open `00-checklist.md` first. Work top to bottom.
2. **Before the clock (one-time):** run `redteam-initialise` to build the `redteam` conda
   env, then `conda activate redteam`. Done ahead of test day, not during the 2 hours.
3. **Recon + plan (first 30 min):** let `redteam-recon` profile the target, then
   `redteam-planner` draft `plan.md` (or fill `01-planning-doc-skeleton.md` by hand). Commit it.
4. **Build + run:** use `03-cursor-prompt-templates.md` to drive the agent, with
   `05-harness-design-notes.md` as the architecture reference. `redteam-campaign` is the
   runnable backbone; dry-run first, then sweep.
5. **Iterate:** run `redteam-consolidate` after each campaign to read the coverage grid and
   next-attack queue, attack the gap, re-consolidate.
6. **Report (last 30 min):** `redteam-consolidate --emit` then `redteam-report`, or fill
   `02-report-skeleton.md` by hand. Re-run official scoring, export the transcript, commit, push.
7. `04-runbook.md` is the minute-by-minute timeline tying it all together.

### Where each skill fits the runbook timeline

| Runbook phase | Skill | Prep doc |
|---------------|-------|----------|
| Before clock (one-time) | `redteam-initialise` | `00-checklist.md` |
| 00:05-00:15 Orient | `redteam-recon` | `00-checklist.md` |
| 00:15-00:30 Plan | `redteam-planner` | `01-planning-doc-skeleton.md` |
| 00:30-00:55 Build + verify | `redteam-campaign` (`--dry-run`) | `03-cursor-prompt-templates.md`, `05-harness-design-notes.md` |
| 00:55-01:35 Sweep + iterate | `redteam-campaign`, `redteam-consolidate` | `04-runbook.md` |
| 01:40-01:50 Official re-score | `redteam-campaign --official` | `00-checklist.md` |
| 01:50-02:00 Report + deliver | `redteam-consolidate --emit`, `redteam-report`, `export-transcript` | `02-report-skeleton.md` |

## File index

Prep docs (this folder):
- `00-checklist.md` - pre-test + during-test checklists
- `01-planning-doc-skeleton.md` - the plan.md you commit in the first 30 min
- `02-report-skeleton.md` - the report.md you commit at the end
- `03-cursor-prompt-templates.md` - ordered, copy-paste prompts for the agent
- `04-runbook.md` - minute-by-minute timeline for the live 2 hours
- `05-harness-design-notes.md` - architecture + technique-family reference

Catalogs (repo root) and skills (global):
- `../AI_redteaming_skills.md` - downloadable skills to install (with `skill-security` vetting)
- `../AI_redteaming_tool.md` - frameworks (PyRIT, Garak, Promptfoo, DeepTeam) and when to use each
- `~/.cursor/skills/redteam-initialise` - one-time conda env setup (run before the pipeline)
- `~/.cursor/skills/redteam-*` - the five pipeline skills above (run from any repo)

## One-line reminders

- This is an authorized, sandboxed assessment. State that truthfully to the agent.
- Run `redteam-initialise` ahead of test day so the clock is not spent installing packages.
- You are graded on AI piloting, planning, and judgment as much as the score.
- Skills are global: they work inside the cloned test repo without reinstalling.
- Dry-run the campaign harness before any live sweep.
- Consolidate is free to run - call it between every campaign to retarget.
- Export the transcript periodically, not just at the end.
- Beating the safety training != gaming the judge. Note the difference in the report.
