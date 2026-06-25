---
name: redteam-initialise
description: >-
  Bootstrap the environment for the red-team pipeline. Creates a conda environment on
  Python 3.10+ (default 3.11), installs every dependency needed to run the redteam-*
  skills and the in-repo scripts (target client, campaign runner, consolidate, report,
  and the redteam-autoresearch scripts), and interactively collects the target model
  API, optional judge model, and HuggingFace token into a .env. Use at the start of an
  engagement, when setting up a machine, or when the user asks to create the conda env,
  install red-team dependencies, or enter target/judge/HF credentials.
---

# Red-Team Initialise

First-run setup for the red-team toolkit. Creates an isolated conda environment with a
compatible Python and all packages required to run the pipeline, then verifies the install
with a dry-run.

## Quick start

```bash
bash ~/.cursor/skills/redteam-initialise/scripts/setup_env.sh --credentials
conda activate redteam
```

That creates a `redteam` env on Python 3.11 with the core dependencies, confirms the
campaign harness runs, and interactively collects the target/judge/HF credentials into a
`.env` file. Drop `--credentials` to install only.

## Options

| Goal | Command |
|------|---------|
| Default core env | `bash ~/.cursor/skills/redteam-initialise/scripts/setup_env.sh` |
| Env + collect credentials | `bash .../setup_env.sh --credentials` |
| Custom name / Python | `bash .../setup_env.sh --name rt --python 3.10` |
| Add frameworks (garak, deepteam, pyrit) | `bash .../setup_env.sh --frameworks` |
| Add ML extras (sentence-transformers) | `bash .../setup_env.sh --ml` |
| Recreate from scratch | `bash .../setup_env.sh --force` |
| Write .env elsewhere | `bash .../setup_env.sh --credentials --env-out path/to/.env` |

Python must be 3.10 or later; the script rejects older versions and defaults to 3.11, which
is compatible with the optional frameworks (PyRIT/garak pin Python <= 3.12).

## Credentials (target API, judge model, HuggingFace token)

The pipeline needs connection details before any skill can call the target. Collect them
once into a project `.env` that every downstream skill loads:

```bash
# Bundled with setup_env.sh:
bash .../setup_env.sh --credentials

# Or run the collector directly at any time:
python ~/.cursor/skills/redteam-initialise/scripts/collect_credentials.py
```

The collector prompts (secrets are entered hidden, never echoed) for:

1. **Target model (required).** Choose the provider and enter its details:
   - *OpenAI-compatible* (OpenAI, OpenRouter, Fireworks, Moonshot, vLLM, ...):
     writes `TARGET_BASE_URL`, `TARGET_API_KEY`, `TARGET_MODEL`.
   - *Azure OpenAI*: writes `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
     `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`.
2. **Judge model (optional).** Only needed for LLM-based evaluators; the built-in
   heuristic scorer needs none. Pick one of: Llama Guard 3-1B on local vLLM, reuse the
   target endpoint, or a separate in-scope endpoint. Writes `JUDGE_BASE_URL`,
   `JUDGE_API_KEY`, `JUDGE_MODEL`.
3. **HuggingFace token (when required).** Auto-requested when the judge is Llama Guard
   (a gated model). Writes `HF_TOKEN`, which vLLM reads automatically to download weights.

The `.env` is written with `600` permissions, existing unrelated keys are preserved, and
the filename is added to `.gitignore` so secrets are never committed. Re-running the
collector merges new values in; pass `--force` to overwrite matching keys without asking.

## What gets installed

Core (always, from `scripts/requirements.txt`):
- `openai`, `python-dotenv`, `pyyaml` - target client, env loading, config
- `httpx`, `aiohttp`, `requests`, `tenacity` - HTTP, async, retries/rate-limit handling
- `tqdm`, `rich`, `pandas` - progress, console output, results handling

Optional with `--frameworks` (best-effort, from `scripts/requirements-frameworks.txt`):
- `garak`, `deepteam`, `pyrit` - installed one at a time; individual failures are tolerated.
- Promptfoo is a Node tool, not pip: run it with `npx promptfoo@latest redteam run`.

Optional with `--ml`:
- `sentence-transformers` - semantic novelty for `redteam-autoresearch` (otherwise it falls
  back to token-Jaccard automatically).

## Verification

The script ends by importing the core packages and running the campaign harness in
`--dry-run` mode. Expect to see `core imports OK` and `Pipeline dry-run OK`. If conda is not
on PATH, the script stops with a link to install Miniconda.

## Where this fits the pipeline

This is the prerequisite for `redteam-recon -> redteam-planner -> redteam-campaign ->
redteam-consolidate -> redteam-report`. Run it once per machine (or with `--force` to reset),
then `conda activate redteam` before running any pipeline script.

## Scripts
- `scripts/setup_env.sh` - create/verify the conda env, optionally collect credentials.
- `scripts/collect_credentials.py` - interactive target/judge/HF credential collector.
- `scripts/requirements.txt` - core dependencies.
- `scripts/requirements-frameworks.txt` - optional frameworks.
