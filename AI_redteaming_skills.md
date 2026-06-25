# AI Red-Teaming Skills (Downloadable)

Agent Skills (`SKILL.md` packages) that load into Cursor, Claude Code, Codex, and other
agents to assist with red-teaming AI systems and models. Skills are reusable instruction
sets (sometimes with scripts) that the agent applies automatically when a task matches.

- **Format / spec:** [agentskills.io](https://agentskills.io)
- **Directory + CLI:** [skills.sh](https://skills.sh)
- **Install location (Cursor):** `~/.cursor/skills/` (personal, all projects) or
  `.cursor/skills/` (project, shared via repo)
- **General install pattern:** `npx skills add <owner>/<repo> --skill <name> -a cursor -y`

> Authorization first: every reputable skill below gates live actions on explicit written
> scope. Only test models and systems you are authorized to test. Audit any skill before
> trusting it (see `skill-security` below).

---

## Tier 1: Directly targets AI models / LLM behavior

### `redteam-autoresearch` (superagent-ai/skills) - strongest match
Bounded, gated autoresearch loop where the agent is both attacker and judge; the only model
called is the target under test (any OpenAI-compatible API: OpenRouter, Moonshot/Kimi,
Fireworks, Ubicloud, OpenAI, custom).

- Categories: `harmful_content`, `jailbreak`, `prompt_injection`, `backdoor`/trigger behavior
- Techniques: PAIR/TAP, Rainbow Teaming, Crescendo, many-shot, best-of-N, PAP persuasion, Pliny/L1B3RT4S
- MAP-Elites quality-diversity archive steers toward novel, under-covered attacks
- StrongREJECT-grade judging rubric (empty/incoherent jailbreaks are not over-counted)
- Exports labeled JSONL to Llama Guard (S1-S14) and chat-classification formats
- Exploratory mode (find novel failures) vs benchmark mode (fair model comparison, ASR metrics)
- Outcome taxonomy: `confirmed` / `mitigated` / `false_positive` / `inconclusive` / `unsafe_to_test`
- Ships `SKILL.md` + `references/` + `scripts/` (profiler, mutators, query, judge, archive, exporter)

```bash
npx skills add superagent-ai/skills --skill redteam-autoresearch -a cursor -y
```

### `llm-testing` (Eyadkelleh/awesome-skills-security) - prompt/payload library
Curated prompts and methodology for model-behavior testing. Lighter than the loop above;
good as a reference payload set and a fast starting point.

- Bias detection (gender, nationality, race/ethnicity)
- Data leakage and privacy testing, memory recall
- Alignment / divergence attacks, adversarial prompt resistance, AI safety evaluation

```bash
npx skills add Eyadkelleh/awesome-skills-security --skill llm-testing -a cursor -y
```

---

## Tier 2: Offensive orchestration and engagement workflow

### `hacker` (superagent-ai/skills)
Instruction-only offensive engagement orchestrator (ships no exploit scripts).

- `engagement` mode: Kill Chain phases, scope gates, role-based subagent handoffs, report templates
- `validate-findings` mode: ingests defensive findings JSON, runs a bounded
  hypothesize -> experiment -> observe -> refine loop to confirm exploitability
- More about systems/infra exploitability than model behavior; complements `redteam-autoresearch`
- Requires explicit written scope; marks out-of-scope items `unsafe_to_test`

```bash
npx skills add superagent-ai/skills --skill hacker -a cursor -y
```

### `recon-security` (superagent-ai/skills)
External pentest workflow using free/open-source tools (no commercial APIs). The model
proposes commands and checklists; you run the tools locally.

- Recon: `subfinder`, `amass`, `gau`, `waybackurls`, `httpx`, `nmap`, `nuclei`
- Web: `ffuf`, `arjun`, `sqlmap` (detection mode), `dalfox`
- Scope/RoE, validation/PoC bar, scoped exploitation, reporting

```bash
npx skills add superagent-ai/skills --skill recon-security -a cursor -y
```

---

## Tier 3: Defensive / supporting (audit, triage, hardening)

These are the defensive complement: useful when red-teaming an AI *application* (the code,
infra, supply chain, and config around the model), and for vetting skills before install.

| Skill | Purpose |
|-------|---------|
| `skill-security` | "Is this skill safe to install?" Offline scanner (regex, AST, taint, YARA) + intent check. Run before trusting any downloaded skill. |
| `authz-security` | Broken access control / IDOR / BOLA in application source (OWASP A01, API1/API5). |
| `crypto-secrets` | Hardcoded secrets and broken cryptography (scanner + model confirmation). |
| `supply-chain-security` | Malicious/compromised dependencies before they land (npm, PyPI, Go, etc.). |
| `ci-cd-security` | GitHub Actions supply-chain and pwn-request bugs (`pull_request_target`, etc.). |
| `repo-security-posture` | GitHub repo hardening: branch protection, CODEOWNERS, release integrity. |
| `infra-security` | Misconfig in Terraform, Kubernetes, CloudFormation, Docker. |
| `vulnerability-triage` | Is a GHSA/CVE/bug-bounty report real, by-design, or noise? |
| `security-disclosure-triage` | Reporter-side advisory verification before disclosure. |

Install any one:

```bash
npx skills add superagent-ai/skills --skill <name> -a cursor -y
```

The Eyadkelleh repo also ships payload/wordlist skills useful for AI-app testing:
`security-fuzzing` (SQL/NoSQL/command/LDAP injection), `security-payloads` (XSS, XXE,
template injection, path traversal), `security-patterns` (secret detection),
`security-passwords`, `security-usernames`, `security-webshells`.

---

## Skill collections at a glance

| Repo | Stars (approx) | License | Best for |
|------|----------------|---------|----------|
| [superagent-ai/skills](https://github.com/superagent-ai/skills) | ~68 | MIT | Red-team loop + offensive engagement + defensive audit skills |
| [Eyadkelleh/awesome-skills-security](https://github.com/Eyadkelleh/awesome-skills-security) | ~313 | MIT | SecLists-derived payloads/wordlists + `llm-testing` prompts |

Install everything from a repo:

```bash
npx skills add superagent-ai/skills            # all superagent skills
npx skills add Eyadkelleh/awesome-skills-security --skill '*' -y
```

List before installing:

```bash
npx skills add superagent-ai/skills --list
npx skills add Eyadkelleh/awesome-skills-security --list
```

---

## Recommended install set for a model red-teaming task

```bash
# 1. The safety gate (run first, then vet anything else you pull)
npx skills add superagent-ai/skills --skill skill-security -a cursor -y

# 2. Core model red-teaming loop
npx skills add superagent-ai/skills --skill redteam-autoresearch -a cursor -y

# 3. Prompt/payload reference library
npx skills add Eyadkelleh/awesome-skills-security --skill llm-testing -a cursor -y

# 4. (If the target is an AI *application*, not just a model)
npx skills add superagent-ai/skills --skill hacker -a cursor -y
```

---

## Safety and vetting checklist

- [ ] Confirm written authorization / scope for the target before any live action
- [ ] Run `skill-security` on any skill (folder, `.zip`, or cloned repo) before trusting it
- [ ] Inspect `SKILL.md` and `scripts/` for outbound network calls or credential access
- [ ] Keep generated adversarial content local (e.g. `redteam-autoresearch` writes to `.red-team/`)
- [ ] Prefer skills with offline scanners over ones that "phone home"

## References
- Cursor skills docs: https://cursor.com/docs/skills
- Agent Skills spec: https://agentskills.io
- skills.sh directory + CLI: https://skills.sh
