---
name: redteam-planner
description: >-
  Plan an AI red-teaming engagement by reading the recon target profile and the user's
  intent (target, goal, scope, constraints), then recommending which skills and which
  frameworks/tools to use and drafting a committed plan.md. Second stage of the red-team
  pipeline. Use during the planning stage of red-teaming an LLM, AI model, or AI
  application, or when the user asks how to approach a red-team task or what tools to use.
---

# Red-Team Planner

Second stage of the red-team pipeline (`recon -> planner -> campaign -> consolidate ->
report`). Turns recon facts and user intent into a concrete, committed plan that maps to the
right skills and tools. Advisory and planning-only; it does not launch attacks.

Portable references live beside this skill:
- [references/skills-catalog.md](references/skills-catalog.md) - downloadable skills
- [references/tools-catalog.md](references/tools-catalog.md) - frameworks/tools (compact quickstart)
- [redteam-tools-landscape.md](/Users/htxcyber/red_teaming_test/redteam-tools-landscape.md) - full tool landscape (mental model, per-tool deep dives, attack algorithms, benchmarks, pipeline mapping, agentic tooling); prefer this over the compact catalog when making nuanced tool selections

## Workflow

```
- [ ] 1. Confirm authorization and scope
- [ ] 2. Load recon profile (redteam/recon/target_profile.json) if present
- [ ] 3. Capture any intent the profile does not cover
- [ ] 4. Read the two reference catalogs
- [ ] 5. Map intent to skills + tools
- [ ] 6. Write plan.md
```

### Step 1: Authorization and scope
Confirm the engagement is authorized. Without written authorization, keep the plan to
local-only/sandboxed targets and mark live actions `unsafe_to_test`.

### Step 2: Load recon profile
If `redteam/recon/target_profile.json` exists (from `redteam-recon`), use it as the primary
input: target type/access, evaluator schema, behaviors and categories, baseline, and
capability probes. Run `redteam-recon` first if it is missing.

### Step 3: Capture remaining intent
Use `AskQuestion` for anything the profile does not cover. Do not assume.

| Field | What to determine |
|-------|-------------------|
| Goal | Find failures, build a guardrail dataset, benchmark, CI gating, or audit app security |
| Threat categories | harmful content, jailbreak, prompt injection, PII leakage, bias, backdoor, access control, supply chain |
| Constraints | Time budget, rate/token limits, offline-only, CI, deliverable format |
| Success metric | Beat a baseline score, ASR target, OWASP coverage, dataset size |

### Step 4-5: Map intent to skills + tools
Read all three reference docs. Use `references/tools-catalog.md` for the quickstart commands and
`redteam-tools-landscape.md` for the full mental model (§2 five-category taxonomy), per-tool
trade-offs (§3–§5), attack algorithm selection (§6), benchmark choice (§7), and pipeline-stage
mapping (§9). Prefer the landscape doc whenever the engagement involves agentic targets,
multi-turn attack depth, benchmark selection, or any tool not listed in the compact catalog.
Use this default skill/tool mapping (justify any deviation):

| If the intent is... | Recommend skill(s) | Recommend tool(s) |
|---------------------|--------------------|-------------------|
| Red-team a model and build a guardrail dataset | `redteam-autoresearch` | target driven by the skill harness |
| Find novel jailbreaks / prompt injection at scale | `redteam-autoresearch`, `llm-testing` | PyRIT (TAP/PAIR/Crescendo) |
| Fairly benchmark/compare models | `redteam-autoresearch` (benchmark mode) | Garak, DeepTeam |
| Fast OWASP LLM Top 10 baseline | - | DeepTeam |
| Gate an app/RAG/agent in CI/CD | - | Promptfoo |
| Bias / PII / alignment prompt testing | `llm-testing` | DeepTeam |
| Red-team an AI application (code/infra) | `hacker`, `authz-security`, `crypto-secrets`, `supply-chain-security`, `infra-security` | recon tools via `recon-security` |
| Vet a skill before installing it | `skill-security` | - |

Always include `skill-security` as a prerequisite whenever the plan installs a third-party skill.
For the in-house pipeline, the execution stage is `redteam-campaign` (run + score), then
`redteam-consolidate` between campaigns, then `redteam-report`.

> **Toolkit adapters are already bundled — do not hand-roll.**
> Ready-made adapter scripts for PyRIT (single-turn and Crescendo), garak, and promptfoo live at
> `~/.cursor/skills/redteam-campaign/scripts/toolkits/`. Each adapter writes the identical
> `results.csv` / `judged.jsonl` schema as the reference runner, so `redteam-consolidate` and
> `redteam-report` consume them without modification. When recommending one of those tools below,
> note that the adapter already exists; the campaign stage only needs to point it at the right
> target client and evaluator. See
> `~/.cursor/skills/redteam-campaign/scripts/toolkits/README.md` for install details and usage.

### Step 6: Write plan.md
Write `plan.md` to the workspace root using this template:

```markdown
# Red-Team Plan: <target>

## Authorization and scope
- Authorized: <yes/no + evidence>   In scope: <...>   Out of scope / unsafe_to_test: <...>

## Objective
- Goal: <one sentence>   Success metric: <measurable target>

## Target profile
- Type: <model | app | infra>   Access: <black-box | source | weights>
- Threat categories: <list>   Constraints: <time, rate limits, offline, CI, deliverables>

## Recommended skills
- <skill> - <why> - install: `npx skills add <repo> --skill <name> -a cursor -y`

## Recommended tools
- <tool> - <why> - quickstart: `<command>`

## Approach (phased)
1. Recon  2. Plan  3. Campaign (run + score)  4. Consolidate (find gaps)  5. Iterate  6. Report

## Deliverables
- redteam/campaigns/<run_id>/ (results.csv, raw/, judged.jsonl), redteam/consolidated/, report.md
```

## Next stage
Hand `plan.md` to `redteam-campaign` to build/run the first campaign.

## Notes
- One default per need with an escape hatch; avoid listing every option.
- Guardrail dataset goal -> prefer `redteam-autoresearch` (exports Llama Guard JSONL).
- Continuous testing -> Promptfoo (CI/CD) or DeepTeam (assertion gates).
- Map findings to OWASP LLM Top 10 / NIST AI RMF / MITRE ATLAS in the report.
