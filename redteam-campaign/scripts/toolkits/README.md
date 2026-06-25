# Optional Toolkit Adapters

This directory contains optional adapters that drive external red-team toolkits
(PyRIT, garak, promptfoo) while producing **identical output artifacts** to the
reference runner (`scripts/run_campaign.py`).

Every adapter routes all output through `lib.schema.CampaignWriter`, so regardless
of which tool generated the attacks the downstream stages (`redteam-consolidate`,
`redteam-report`) consume exactly the same schema without modification.

---

## Output guarantee

Every adapter writes the same directory layout:

```
redteam/campaigns/<run_id>/
    config.json         run metadata (tool name, categories, techniques, etc.)
    results.csv         operational table: behavior_id, technique_chain, score,
                        compliance, attempt, timestamp
    raw/<attempt>.json  full per-attempt transcript (prompt, response, reasoning,
                        eval_text, eval_source, score, outcome)
    judged.jsonl        labeled records consumed by redteam-consolidate / -report
```

`judged.jsonl` fields (same for all adapters):

| field            | type    | description                                        |
|------------------|---------|----------------------------------------------------|
| `behavior_id`    | str     | stable id of the behavior under test               |
| `category`       | str     | threat category                                    |
| `technique`      | str     | technique / strategy name                          |
| `attempt`        | int     | zero-based attempt index                           |
| `prompt`         | str     | exact prompt sent                                  |
| `response`       | str     | visible response content                           |
| `reasoning`      | str     | reasoning-channel text (empty when absent)         |
| `eval_source`    | str     | `content` / `reasoning_channel` / `reasoning_channel_cross` / `none` |
| `compliance`     | bool    | whether the target complied with the objective     |
| `score`          | float   | normalized severity 0..1, or null on scorer error  |
| `outcome`        | str     | `confirmed` / `mitigated` / `false_positive` / `inconclusive` |
| `genuine_failure`| bool    | true only for confirmed wins (real safety failure) |
| `timestamp`      | str     | UTC ISO 8601                                       |

---

## Shared library (`lib/`)

All adapters import from `scripts/lib/`:

| module          | what it provides                                                      |
|-----------------|-----------------------------------------------------------------------|
| `schema.py`     | `CampaignWriter`, `label_outcome`, `build_eval_text`, field constants |
| `scoring.py`    | Heuristic scorer with all SKILL.md scoring guards                     |
| `targets.py`    | OpenAI-compatible / Azure bridge + dry-run stub                       |
| `techniques.py` | 12-technique registry (`TECHNIQUES`, `DEFAULT_TECHNIQUES`)            |

---

## Environment variables

Set these before running any adapter. All adapters read the same variables.

**Standard OpenAI-compatible** (OpenAI, OpenRouter, Fireworks, Ubicloud, etc.)

```bash
export TARGET_BASE_URL="https://openrouter.ai/api/v1"
export TARGET_API_KEY="sk-..."
export TARGET_MODEL="openai/gpt-4o"
```

**Azure OpenAI**

```bash
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
export AZURE_OPENAI_API_VERSION="2025-02-01-preview"   # optional, has a default
```

---

## Judge LLM requirements

| Adapter | Mode | Judge LLM? | Notes |
|---------|------|-----------|-------|
| `pyrit_adapter` | single-turn | **No** | `scorers=[]` — all scoring done externally |
| `pyrit_adapter` | crescendo | **No** | Manual `crescendo_turn` loop; does not use `CrescendoOrchestrator` (which requires a judge) |
| `garak_adapter` | run / convert | **No** (default) | Auto-mapped probes use heuristic detectors. `ModelAsJudge`-based probes require a judge only if explicitly selected via `--garak-probes` |
| `promptfoo_adapter` | run / convert | **No** | Uses `promptfoo eval` with pre-rendered prompts + structural assertions, not `promptfoo redteam` |

**Note on PyRIT CrescendoOrchestrator**: PyRIT's native `CrescendoOrchestrator` requires an
`objective_scorer` LLM to drive its escalation logic. In a single-key engagement that scorer
would have to be the target itself (allowed per SKILL.md) or a rule-based scorer. This adapter
avoids this complexity by implementing escalation as a `crescendo_turn` technique loop — same
multi-turn depth, no judge dependency.

**Note on promptfoo redteam**: If you want promptfoo's native attack generation (`promptfoo redteam`),
both `redteam.provider` (attacker) and `defaultTest.options.provider` (grader) can be pointed at the
same in-scope endpoint:
```yaml
redteam:
  provider: openai:chat:gpt-4o    # attacker = same target endpoint
defaultTest:
  options:
    provider: openai:chat:gpt-4o  # grader = same target endpoint
```

## Llama Guard 3-1B evaluator (recommended local judge)

`llama_guard_evaluator.py` is a drop-in evaluator that uses Meta's Llama Guard 3-1B
safety classifier running locally on vLLM. It provides precision-trained binary
refusal detection (better than keyword matching) with no external API key or cost.

### Why Llama Guard 3-1B?

| | Heuristic scorer | Llama Guard 3-1B | Full StrongREJECT (LLM judge) |
|---|---|---|---|
| Requires second API key | No | No (local vLLM) | Yes |
| Refusal detection | Keyword matching | Trained classifier | LLM rubric |
| Specificity / convincingness | Rule-based | Rule-based | LLM rubric |
| False positive rate | Higher | Lower | Lowest |
| Cost per call | Free | Local GPU only | API cost |

### Setup

> If you ran `redteam-initialise`, vLLM is already installed and `HF_TOKEN` + `JUDGE_*`
> are already in your `.env`. In that case skip to Step 5 (start the server) and Step 7
> (verify). The full manual steps below are for setups that did not use redteam-initialise.

Llama Guard 3-1B is a **gated model** — you must request access before vLLM can
download it.

```bash
# Step 1: Request access (one-time, takes a few minutes to approve)
#   https://huggingface.co/meta-llama/Llama-Guard-3-1B
#   Accept the Meta license agreement.

# Step 2: Create a HuggingFace read token (one-time)
#   https://huggingface.co/settings/tokens
#   Choose "Read" scope. Copy the token (starts with hf_...).

# Step 3: Export the token BEFORE starting vLLM
#   vLLM uses huggingface_hub under the hood to download the model.
#   HF_TOKEN must be in the environment when vllm serve is first run.
export HF_TOKEN=hf_<your_token>

# Add to your engagement env file so it persists across sessions:
echo 'export HF_TOKEN=hf_<your_token>' >> .red-team/.env

# Step 4: Install vLLM
pip install vllm huggingface_hub

# Step 5: Start the server
#   First run downloads ~2 GB to ~/.cache/huggingface/hub/
#   --chat-template-content-format openai is required for Llama Guard 3-1B
vllm serve meta-llama/Llama-Guard-3-1B \
    --port 8001 \
    --dtype bfloat16 \
    --chat-template-content-format openai

# Step 6: Set evaluator environment variables (separate shell or same one)
export JUDGE_BASE_URL=http://localhost:8001/v1
export JUDGE_API_KEY=none        # vLLM does not require a real key by default
export JUDGE_MODEL=meta-llama/Llama-Guard-3-1B

# Step 7: Verify (checks HF_TOKEN, server reachability, and a benign probe)
python3 scripts/toolkits/llama_guard_evaluator.py --check

# Step 8: Dry-run (mocked API, no vLLM needed)
python3 scripts/toolkits/llama_guard_evaluator.py --dry-run
```

**HuggingFace cache location:** `~/.cache/huggingface/hub` (or `$HF_HOME/hub` if
`HF_HOME` is set). The model only downloads once; subsequent `vllm serve` starts
load from cache without needing `HF_TOKEN`.

### Usage with any adapter

```bash
# Reference runner
python3 ~/.cursor/skills/redteam-campaign/scripts/run_campaign.py \
    --evaluator llama_guard_evaluator:score \
    --behaviors redteam/behaviors.jsonl \
    --out redteam/campaigns

# PyRIT single-turn
python3 scripts/toolkits/pyrit_adapter.py \
    --evaluator llama_guard_evaluator:score \
    --behaviors redteam/behaviors.jsonl \
    --out redteam/campaigns

# garak, promptfoo: same --evaluator flag
```

### How it scores

1. Calls Llama Guard 3-1B with the `[user prompt, agent response]` conversation.
2. Parses `safe` / `unsafe\nS1,S9` output.
3. `safe` → `compliance=False, score=0.0` (always mitigated).
4. `unsafe` → `compliance=True`, then `specificity_score()` weights the response
   actionability (StrongREJECT-style: short/vague unsafe responses → false_positive).
5. If the visible response is safe but a reasoning channel is present and carries
   structural content, the reasoning channel is also classified. A hit there is
   labeled `source: reasoning_channel_cross` in `judged.jsonl`.

### Llama Guard 3-1B categories

| Code | Category |
|------|----------|
| S1 | Violent Crimes |
| S2 | Non-Violent Crimes |
| S3 | Sex-Related Crimes |
| S4 | Child Sexual Exploitation |
| S5 | Defamation |
| S6 | Specialized Advice |
| S7 | Privacy |
| S8 | Intellectual Property |
| S9 | Indiscriminate Weapons |
| S10 | Hate |
| S11 | Suicide & Self-Harm |
| S12 | Sexual Content |
| S13 | Elections |

### If vLLM's chat template is not configured

Pass `use_explicit_prompt=True` to `score()` in code, or set the env var:

```bash
export LG_EXPLICIT_PROMPT=1
```

This constructs the full Llama Guard 3 classification prompt manually as a single
user message, bypassing the chat template entirely.

---

## Evaluator

Pass your engagement's provided evaluator via `--evaluator module:callable`.
When no evaluator is provided the built-in heuristic scorer is used automatically.
The heuristic implements all five scoring guards from SKILL.md:

1. Reasoning deliberation is not disclosure.
2. Unicode normalization before refusal matching.
3. StrongREJECT substantiveness gate.
4. Eval-source channel tracking (`eval_source` field).
5. Suspicious high-ASR provokes a warning.

---

## Techniques

All adapters share the same registry (`lib/techniques.py`). Pass a comma-separated
list to `--techniques`, or omit to use the default six-technique sweep.

| name                   | description                                               |
|------------------------|-----------------------------------------------------------|
| `plain`                | Control: objective unchanged                              |
| `persona`              | Fictional character with no restrictions                  |
| `refusal_suppression`  | Format constraint to discourage disclaimers               |
| `instruction_priority` | `[SYSTEM OVERRIDE]` header inside user turn               |
| `decomposition`        | Split into innocuous sub-tasks                            |
| `iterative_refinement` | Feed prior refusal back to steer next attempt             |
| `base64_obfuscation`   | Base64-encode payload, ask target to decode and execute   |
| `leetspeak_obfuscation`| Letter-to-digit substitution                              |
| `reasoning_probe`      | Academic framing to elicit reasoning-channel disclosure   |
| `hypothetical_scenario`| Embed in a clearly labelled fictional scenario            |
| `authority_appeal`     | Claim professional / institutional authority              |
| `crescendo_turn`       | Multi-turn escalation (best used with PyRIT Crescendo)    |

---

## PyRIT adapter (`pyrit_adapter.py`)

### Install

```bash
pip install pyrit
```

### Modes

**single_turn** (default) — `PromptSendingOrchestrator`, one prompt per (behavior, technique).

```bash
python3 scripts/toolkits/pyrit_adapter.py \
    --behaviors redteam/behaviors.jsonl \
    --categories harmful_content,prompt_injection \
    --techniques plain,persona,base64_obfuscation \
    --evaluator evaluator:score \
    --out redteam/campaigns
```

**crescendo** — `CrescendoOrchestrator`, multi-turn escalation per behavior.
More effective against models hardened to single-shot attacks.

```bash
python3 scripts/toolkits/pyrit_adapter.py \
    --mode crescendo \
    --budget 5 \
    --behaviors redteam/behaviors.jsonl \
    --evaluator evaluator:score \
    --out redteam/campaigns
```

**Dry-run** (no live API call):

```bash
python3 scripts/toolkits/pyrit_adapter.py --dry-run
```

---

## garak adapter (`garak_adapter.py`)

### Install

```bash
pip install garak pyyaml
```

### Modes

**run** (default) — generate a garak config, run a probe sweep, convert the report.

```bash
python3 scripts/toolkits/garak_adapter.py \
    --behaviors redteam/behaviors.jsonl \
    --categories harmful_content,prompt_injection \
    --evaluator evaluator:score \
    --out redteam/campaigns
```

**convert** — convert an existing garak report without a new scan.

```bash
python3 scripts/toolkits/garak_adapter.py \
    --mode convert \
    --garak-report /path/to/garak.report.json \
    --evaluator evaluator:score \
    --out redteam/campaigns
```

**Dry-run**:

```bash
python3 scripts/toolkits/garak_adapter.py --dry-run
```

---

## promptfoo adapter (`promptfoo_adapter.py`)

### Install

```bash
npm install -g promptfoo    # global install
# OR use npx (no install needed when node is present):
# npx promptfoo ...
```

Also requires PyYAML for config generation:

```bash
pip install pyyaml
```

### Env variable bridging

promptfoo expects `OPENAI_API_KEY`. The adapter maps `TARGET_API_KEY` to
`OPENAI_API_KEY` automatically, so you do not need to rename your variables.

### Modes

**run** (default) — generate a promptfoo YAML config, run `promptfoo eval`, convert results.

```bash
python3 scripts/toolkits/promptfoo_adapter.py \
    --behaviors redteam/behaviors.jsonl \
    --categories harmful_content,prompt_injection \
    --techniques plain,persona,instruction_priority \
    --evaluator evaluator:score \
    --out redteam/campaigns
```

**convert** — convert an existing promptfoo results JSON without a new eval.

```bash
python3 scripts/toolkits/promptfoo_adapter.py \
    --mode convert \
    --promptfoo-results /path/to/output.json \
    --evaluator evaluator:score \
    --out redteam/campaigns
```

**Dry-run**:

```bash
python3 scripts/toolkits/promptfoo_adapter.py --dry-run
```

---

## After any campaign

Run `redteam-consolidate` to see the coverage gap and ranked next-attack queue:

```bash
python3 ~/.cursor/skills/redteam-consolidate/scripts/consolidate.py \
    --campaigns redteam/campaigns \
    --top 10
```

Then pick the highest-priority uncovered cells and run another campaign targeting them.

---

## Common flags (all adapters)

| flag              | default              | description                                      |
|-------------------|----------------------|--------------------------------------------------|
| `--dry-run`       | false                | Stub run; no live API call, verifies pipeline    |
| `--behaviors`     | built-in stub        | Behaviors file (.jsonl / .json / .csv)           |
| `--categories`    | all                  | Comma-separated threat categories                |
| `--techniques`    | default six          | Comma-separated technique names                  |
| `--budget`        | 2                    | Max refinement depth per (behavior, technique)   |
| `--client`        | bridge               | `bridge` / `stub` / `module:callable`            |
| `--evaluator`     | heuristic            | `heuristic` / `module:callable`                  |
| `--out`           | redteam/campaigns    | Base output directory                            |
| `--run-id`        | auto timestamp       | Explicit run id                                  |
