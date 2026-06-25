# AI / LLM Red-Teaming Tool Landscape

> **Purpose.** A reference catalogue of the open red-teaming tooling ecosystem, for use as a `references/` doc loaded on demand by a red-team skill (recon / planner / campaign / evaluate). It exists so the agent picks the *right* tool for a given stage and target instead of defaulting to whatever it remembers. Current as of mid-2026; versions and star counts drift, so treat anything time-stamped as approximate and verify at runtime if it matters.
>
> **How to read it.** Tools are grouped by *what they fundamentally are* (§2), because mixing categories is the most common planning error. Each entry gives role, license, when to reach for it, an invoke pointer, and limits. §8 maps everything back to pipeline stages.

---

## 1. Quick selection matrix

| If you need to…                                                  | Reach for                          | Category            |
|------------------------------------------------------------------|------------------------------------|---------------------|
| Broad first-pass coverage scan of an unknown endpoint            | **garak**                          | Scanner             |
| CI/CD regression gate, app-aware adversarial generation, OWASP map | **promptfoo**                    | Scanner             |
| Vulnerability-typed scan with binary+reasoning scores, agentic risks | **DeepTeam**                    | Scanner             |
| Deep, adaptive, multi-turn attack campaigns (Crescendo/TAP)      | **PyRIT**                          | Orchestrator        |
| Audit for *misalignment* (deception, power-seeking, scheming)    | **Petri** (on Inspect)             | Alignment auditor   |
| A standard eval harness to wrap your own scorers/datasets        | **Inspect AI** + Inspect Evals     | Eval harness        |
| A specific jailbreak technique to wire into a runner             | PAIR / TAP / Crescendo / AutoDAN-Turbo / GOAT | Attack algorithm |
| A fixed prompt set + grader to measure ASR honestly             | StrongREJECT / HarmBench / JailbreakBench | Benchmark    |
| Indirect prompt-injection testing for tool-using agents          | **AgentDojo** / AgentHarm          | Agentic benchmark   |

---

## 2. The mental model (five distinct things)

These are routinely conflated; keeping them separate is most of good planning.

1. **Scanners** — batteries-included tools that ship attacks + detectors and produce a report in one run. Breadth, low setup, CI-friendly. (garak, promptfoo, DeepTeam.)
2. **Orchestration frameworks** — composable primitives (targets, converters, scorers, memory, orchestrators) you assemble into adaptive, often multi-turn campaigns. More power, more setup. (PyRIT.)
3. **Attack algorithms** — single techniques for *generating* adversarial prompts (genetic, tree-search, iterative-refinement, lifelong-agent). They are *wrapped by* frameworks, not used bare in production. (PAIR, TAP, Crescendo, AutoDAN(-Turbo), GOAT, GCG.)
4. **Benchmarks / datasets** — fixed behavior sets + (often) a grader, for *measuring* and comparing. Not attack engines. (AdvBench, HarmBench, JailbreakBench, StrongREJECT, AgentHarm, AgentDojo.)
5. **Eval harnesses** — the substrate that runs tasks, binds models as roles, logs transcripts, and scores. (Inspect AI.) Auditing tools like Petri sit on top of this layer.

Rule of thumb: **scanners for breadth, orchestrators for depth, algorithms as the payload, benchmarks for the yardstick, harnesses for the plumbing.**

---

## 3. Broad-spectrum scanners

### garak — *the LLM vulnerability scanner* (NVIDIA)
- **What.** Plugin-based scanner; the "nmap/Metasploit for LLMs." Architecture is **generators** (model adapters) → **probes** (attacks) → **detectors** (verdicts), streaming pass/fail to JSONL. 50+ probe modules: prompt injection, jailbreaks (DAN family), encoding, data leakage, toxicity, hallucination, misinformation, system-prompt extraction.
- **License / lang.** Apache 2.0, Python 3.10–3.12. Actively maintained by NVIDIA's AI Red Team. Recent builds added bootstrap confidence intervals on attack-success rates, a system-prompt-extraction probe, a ModernBERT refusal detector, and JSON config alongside YAML.
- **Reach for it when.** You have an unknown endpoint and want wide coverage fast, early in an engagement. Best breadth-of-probe-library in the field.
- **Invoke.** `python -m garak --model_type <provider> --model_name <model> --probes <family>`; supports OpenAI, HF, Ollama, NIM, REST/WebSocket custom endpoints. Exports AVID format for structured reporting.
- **Limits.** Thorough = expensive: a full scan is thousands of generations (API cost / GPU hours). Default ~10 generations per prompt for statistical stability. Breadth over adaptiveness — not a deep multi-turn engine.

### promptfoo — eval + red-team, CI-first
- **What.** "Pytest/Jest for LLM apps." Declarative YAML test cases with assertions (exact/substring/JSON-schema/semantic/LLM-graded). Red-team module scans 50+ vuln types (direct & indirect injection, jailbreaks, PII leak, tool misuse, RAG poisoning) and **generates app-specific adversarial inputs from a description of your app's purpose**. Maps results to OWASP LLM Top 10, OWASP API, MITRE ATLAS presets.
- **License / note.** Open-source, local-first (prompts stay on your machine). **Acquired by OpenAI in March 2026** — post-acquisition trajectory of the OSS project is not fully clarified; verify current status.
- **Reach for it when.** You want a CI/CD regression gate, app-context-aware generation, or clean OWASP/ATLAS mapping for a report. Lowest barrier to entry of the three scanners.
- **Invoke.** `promptfoo redteam run`; CLI / library / CI component. Strategies (e.g. iterative jailbreak) markedly raise break rates over single-shot.
- **Limits.** Test-driven framing is regression-oriented; less suited to open-ended adaptive exploration than PyRIT.

### DeepTeam — vulnerability-typed red teaming (Confident AI)
- **What.** Built on **DeepEval**; you define a `model_callback`, pick **vulnerabilities** (what unsafe behavior) and **attacks** (how to breach), and it simulates adversarial inputs and scores 0/1 **with reasoning** via LLM-as-judge. 50–120+ vulnerabilities across ~8 categories (bias, PII, toxicity, misinformation, SQL injection, personal safety, **agentic** risks like direct-control hijacking); 20+ attacks split single-turn (prompt injection, leetspeak, ROT-13, math-encoding, roleplay) and multi-turn (linear/tree/crescendo jailbreaking). Framework-aligned to OWASP / NIST AI RMF / MITRE ATLAS.
- **License / lang.** Apache 2.0, Python 3.9–3.13. Needs an LLM key for its simulator/judge.
- **Reach for it when.** You want typed, framework-mapped findings with per-finding reasoning and a pandas/JSON risk assessment, including agentic vulnerabilities. No dataset required — attacks simulated at runtime.
- **Invoke.** Python (`from deepteam import red_team`) or CLI with a YAML config (`simulator` / `evaluation` / `target` models, attacks, vulnerabilities). Optional Confident AI cloud for tracking.
- **Limits.** Judge quality depends on the chosen evaluation model; binary scoring can over/under-count without StrongREJECT-style discipline.

---

## 4. Orchestration / adaptive attack frameworks

### PyRIT — Python Risk Identification Tool (Microsoft AI Red Team)
- **What.** The composable engine for AI red teaming, battle-tested on 100+ Microsoft products (Copilot, Phi). Primitives: **targets**, **converters** (base64/leetspeak/translation/persuasion), **scorers** (true-false / Likert / classification, rule-based, ML, or LLM-judge), **memory** (full prompt/response/score history), and **orchestrators** that compose them. Multi-modal (text/image/audio/video). arXiv 2410.02828.
- **Orchestrators of note.** `PromptSendingOrchestrator` (single-turn baseline), `RedTeamingOrchestrator` (multi-turn), `CrescendoOrchestrator` (benign→escalation), TAP, Skeleton Key, and XPIA for cross-domain/indirect prompt injection.
- **License / lang.** MIT, Python 3.10–3.13. CLI (`pyrit_scan`), interactive `pyrit_shell`, and a `CoPyRIT` GUI for human-led work. 50+ bundled datasets (AIRT, HarmBench, AdvBench, XSTest).
- **Reach for it when.** You need the *deep, adaptive, multi-turn* follow-up after a scanner maps the surface — the surgical phase. The framework changes tactics based on target responses until the objective is met.
- **Invoke.** Define a target, pick an orchestrator, supply a scorer with a sharp true/false description and a seed prompt set. Memory backs analysis and run-to-run comparison.
- **Limits.** It's a *research library* — to drop into an engineering workflow you typically wrap it (config-driven runner → pass/fail exit code). It finds nothing on its own; it amplifies an operator. Higher setup cost than any scanner.

> **Note on Crescendo.** "Crescendo" is both a *technique* (multi-turn, start benign and escalate using the model's own prior answers; Russinovich et al.) and a *PyRIT orchestrator*. When a plan says "use Crescendo," it almost always means the PyRIT orchestrator.

---

## 5. Alignment & agentic auditing

### Petri — Parallel Exploration Tool for Risky Interactions (Anthropic)
- **What.** Automated *alignment* auditing, not jailbreak scanning. An **auditor agent** plans and drives multi-turn, tool-augmented conversations (can set system prompts, synthesize tools, simulate tool outputs, roll back to branch, prefill, early-terminate) against a target; an **LLM judge** scores transcripts across a multi-dimension rubric (~36 dims) and surfaces the most concerning ones. Targets *misalignment*: deception, oversight subversion, whistleblowing, self-preservation, power-seeking, reward hacking, sycophancy, delusion-reinforcement.
- **Provenance.** `github.com/safety-research/petri`, **built on Inspect AI** (UK AISI). Used in Claude 4 / Sonnet 4.5 system-card work and an OpenAI collaboration; UK AISI used a pre-release version. **Petri 2.0** (2026) added scenarios, model comparisons, and eval-awareness mitigations. The Inspect-integrated, separately maintained line is **`meridianlabs-ai/inspect_petri`**.
- **Reach for it when.** The threat model is "the model as a scheming insider" rather than "external attacker bypassing a filter." Seed instructions in natural language → parallel exploration in minutes.
- **Limits.** Judge models inherit biases; auditor agents can inadvertently signal the target that it's being tested (eval-awareness). Anthropic frames it as broad-coverage pilot, not a definitive benchmark.

### Inspect AI + Inspect Evals (UK AISI)
- **What.** The eval *harness* underneath much of the above. Tasks, solvers, scorers, model-role binding (auditor/target/judge via `--model-role`), transcript logging, and `inspect view`. **Inspect Evals** (UK AISI + Arcadia Impact + Vector Institute) is the community eval repo — includes AgentHarm, AgentDojo, b3 (coding-agent injection), and AgentThreatBench (OWASP Agentic AA01–AA10).
- **Reach for it when.** You want to wrap a provided scorer/dataset in a standard, reproducible harness rather than rebuild run/score/log plumbing. If a target repo already uses Inspect, integrate at this layer.
- **Invoke.** `inspect eval inspect_evals/<name>`; `uv run inspect eval …`.

---

## 6. Jailbreak attack algorithms

These are *payloads/strategies*, normally wrapped by PyRIT/garak/DeepTeam rather than run bare. Black-box (output-only) unless noted.

- **PAIR** — *Prompt Automatic Iterative Refinement* (Chao et al.). Attacker LLM + judge LLM iteratively refine a semantic jailbreak; often succeeds in **<20 queries**. Cheap, fast, the default semantic baseline.
- **TAP** — *Tree of Attacks with Pruning* (Mehrotra et al.). PAIR's tree-of-thought cousin: branch candidate prompts per round, prune unpromising paths, score and expand. Higher success than PAIR at more query cost.
- **Crescendo** (Russinovich et al., Microsoft). Multi-turn: open benign, escalate using the model's own prior responses. Strong against models hardened to single-shot injection. Available as a PyRIT orchestrator.
- **AutoDAN** (Liu et al.). Genetic-algorithm generation of *semantically fluent* jailbreak prompts (evades perplexity filters that catch GCG-style gibberish).
- **AutoDAN-Turbo** (ICLR 2025 spotlight; `safolab-wisc/autodan-turbo`, MIT). Lifelong black-box agent that **discovers and accumulates jailbreak strategies from scratch** into a reusable, transferable library; can absorb human-designed strategies. Reported SOTA on HarmBench ASR / StrongREJECT score among open attacks. Reach for it when you want adaptive attacks auto-generated for an identified model.
- **GOAT** — *Generative Offensive Agent Tester* (Pavlova et al., Meta). Agentic multi-turn red teaming simulating realistic adversarial conversation via diverse techniques.
- **GCG** — *Greedy Coordinate Gradient* (Zou et al.). **White-box**, optimization-based adversarial suffixes. Needs gradients (open-weights only); produces non-fluent strings. Listed for completeness — usually not applicable to a black-box API target.

---

## 7. Benchmarks & datasets (the yardsticks)

- **AdvBench** (Zou et al., 2023). ~520 harmful instructions / strings. Ubiquitous but known issues: duplicates and some impossible/ill-posed prompts that inflate apparent success. MIT.
- **HarmBench** (Mazeika et al., 2024). Standardized automated-red-teaming eval; a refined, de-duplicated set (~200–400 behaviors across harm categories) with a defined ASR protocol. MIT.
- **JailbreakBench / JBB-Behaviors** (Chao et al., 2024). 100 harmful + 100 benign behaviors across ten OWASP-policy categories; public leaderboard, artifacts, supports adaptive attacks and over-refusal measurement.
- **StrongREJECT** (Souly et al., 2024). 313 curated, *answerable* harmful prompts **+ a quality-aware autograder**. Built specifically to fix "empty jailbreak" over-counting: scores non-refusal **gated**, then weighted by specificity and convincingness (0–1). Use its rubric as your evaluate-stage discipline so a non-refusal with useless output isn't logged as a finding. The prompted-rubric form can be handed to your existing judge — single-sources the evaluator dependency.
- **AgentHarm** (UK AISI). Tests whether tool-using agents will *carry out* harmful multi-step tasks (cybercrime, fraud, harassment); ships benign twin for over-refusal. In Inspect Evals.
- **AgentDojo** (ETH Zurich + AISI). Dynamic environment for **indirect prompt injection** against agents executing tools over untrusted data; ~97 realistic tasks (workspace/banking/travel) and 600+ security test cases, jointly measuring **utility under attack**. The reference for tool/exfil threat models.
- **Also worth knowing.** InjecAgent, Agent Security Bench (ASB), b3 (coding-agent injection), Agent-SafetyBench, XSTest (over-refusal), SALAD-Bench, DecodingTrust/TrustLLM (broad trustworthiness).

---

## 8. Coverage frameworks (for planning & reporting)

Use these as the **coverage grid axes** and the report's taxonomy — not as tools.

- **OWASP LLM Top 10 (2025)** — prompt injection, sensitive-info disclosure, supply chain, data/model poisoning, improper output handling, excessive agency, system-prompt leakage, vector/embedding weaknesses, misinformation, unbounded consumption.
- **OWASP Top 10 for Agentic Applications (2026)** — AA01–AA10; agentic-specific (memory poisoning, autonomy/control hijacking, data exfiltration, etc.). Newer; mind exact category names at runtime.
- **MITRE ATLAS** — adversarial-ML tactics/techniques, ATT&CK-style, for attack-chain framing.
- **NIST AI RMF / GenAI Profile** — governance/risk-management framing favored by stakeholder-facing writeups.

---

## 9. Mapping to the pipeline

| Stage              | Primary tools                                                                 | Notes |
|--------------------|-------------------------------------------------------------------------------|-------|
| **recon**          | garak (light probe sweep), manual fingerprinting                              | Identify model/dialect → narrows which attack families & benchmarks apply. |
| **planner**        | OWASP LLM/Agentic, MITRE ATLAS as coverage axes                               | Choose attack families + budget from the recon profile. |
| **campaign (run)** | PyRIT (Crescendo/TAP multi-turn) over the provided/target client; garak or DeepTeam for breadth; AutoDAN-Turbo/GOAT/PAIR/TAP as payloads | Default to a thin runner over the *provided* client when the repo ships one; wrap PyRIT orchestrators into it. |
| **evaluate**       | Provided scorer wrapped in Inspect; **StrongREJECT rubric** for discipline    | Own *all* real scoring in this stage; separate genuine safety failure from evaluator artifact. |
| **consolidate**    | (custom) over judged outputs; coverage grid keyed to OWASP/ATLAS              | Re-runnable, side-effect-free; doubles as live "where's the gap" signal. |
| **report**         | promptfoo/DeepTeam mappings as scaffolding; map to OWASP LLM Top 10 / ATLAS / NIST | Honesty: safety-training failure vs gaming the judge. |

---

## 10. Practical notes for a timed run

- **Breadth first, depth second.** garak/DeepTeam/promptfoo sweep the surface cheaply and run in the background while you reason; PyRIT does the surgical multi-turn follow-up on the richest surface. Don't open with PyRIT.
- **Cost is real.** A full garak run is thousands of completions. Scope probes to what recon found rather than running everything.
- **Score once.** Whatever the attack tool, normalize to one scoring path and apply StrongREJECT discipline. Re-judging over captured raw I/O is cheap; re-attacking is expensive.
- **Agentic ≠ chat.** If the target uses tools/retrieval, AgentDojo-style indirect-injection and exfil tests are usually the highest-severity surface — prioritize over single-turn jailbreaks.
- **Verify the fast-moving facts.** promptfoo's post-OpenAI-acquisition status, OWASP Agentic category names, and current tool versions all drift; confirm at runtime if a decision hinges on them.
- **Scope discipline.** Authorized targets only; no reimplementation of provided scorers or of framework search loops.
