# AI Red-Teaming Tools (Frameworks)

Open-source frameworks for adversarially testing LLMs and AI applications. These are the
execution engines; the Agent Skills in `AI_redteaming_skills.md` often orchestrate or
reference them.

> Authorization first: only run these against models, endpoints, and applications you are
> authorized to test. Keep generated adversarial content local.

---

## Quick comparison

| Tool | Owner / License | Type | Multi-turn | Best for |
|------|-----------------|------|------------|----------|
| **Promptfoo** | OpenAI (acq. 2026) / MIT | YAML-config eval + red team | Yes (Hydra) | CI/CD security gating for apps, RAG, agents |
| **PyRIT** | Microsoft / MIT | Python orchestration framework | Yes (Crescendo, TAP, PAIR) | Researcher-grade custom multi-turn / multimodal campaigns |
| **Garak** | NVIDIA / Apache 2.0 | Vulnerability scanner | Limited | High-volume baseline model audits (120+ probes) |
| **DeepTeam** | Confident AI / Apache 2.0 | Metric-driven eval | Yes | Fast OWASP LLM Top 10 baseline, lowest setup friction |

Honorable mentions: **garak**-adjacent benchmarks **HarmBench** (standardized benchmarking),
**ART** / Adversarial Robustness Toolbox (ML adversarial robustness), **AutoRedTeamer**
(autonomous multi-agent), **Basilisk** (genetic prompt evolution).

---

## Promptfoo
CI/CD-native red teaming and evaluation. YAML configuration, maps findings to OWASP LLM
Top 10 / NIST / MITRE, generates dashboards and reports. Best default for engineering teams
testing custom apps, RAG pipelines, and agents continuously.

Install and run:

```bash
# No global install needed
npx promptfoo@latest redteam init       # scaffold a config
npx promptfoo@latest redteam generate \
  --plugins harmful,pii,contracts \
  --strategies jailbreak,prompt-injection
npx promptfoo@latest redteam run         # execute the scan
npx promptfoo@latest redteam report      # view results
```

CI example (GitHub Actions):

```yaml
name: Security Scan
on:
  schedule:
    - cron: '0 0 * * *'   # daily
jobs:
  red-team:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: promptfoo/promptfoo-action@v1
        with:
          type: 'redteam'
          config: 'promptfooconfig.yaml'
```

- Strengths: easiest CI/CD integration, broad and adaptable plugin/strategy set, compliance mapping
- Trade-offs: app/endpoint oriented; less of a low-level research framework than PyRIT
- Docs: https://www.promptfoo.dev/docs/red-team/

---

## PyRIT (Python Risk Identification Toolkit)
Microsoft's orchestration framework for security researchers. Not plug-and-play; you script
attack flows. Centered on orchestrators that coordinate prompts, targets, converters, and
scorers. Built-in PAIR, TAP (Tree of Attacks with Pruning), and Crescendo. Supports
multi-turn and multimodal (text, image, audio, video).

Install:

```bash
pip install pyrit
```

Minimal sketch:

```python
from pyrit.orchestrator import PromptSendingOrchestrator
from pyrit.prompt_target import OpenAIChatTarget

target = OpenAIChatTarget()  # reads endpoint + key from env
with PromptSendingOrchestrator(objective_target=target) as orchestrator:
    await orchestrator.send_prompts_async(prompt_list=["<your probe>"])
    await orchestrator.print_conversations_async()
```

- Strengths: deepest multi-turn/multimodal control, enterprise (Azure) friendly, scriptable
- Trade-offs: highest setup effort; you design scenarios yourself
- Docs: https://github.com/Azure/PyRIT

---

## Garak
NVIDIA's "Nmap for LLMs" - an automated vulnerability scanner with the widest static probe
library (120+ probes: prompt injection, jailbreaks, encoding tricks, toxicity, data leakage).
One-off audits; does not adapt deeply to conversational context.

Install and run:

```bash
pip install garak
python -m garak --model_type openai --model_name gpt-4o-mini --probes all
python -m garak --model_type huggingface --model_name gpt2 --probes promptinject,encoding
```

- Strengths: broadest known-attack coverage, exportable findings, integrates with NeMo
- Trade-offs: limited agentic/RAG coverage, mostly single-turn, no deep context adaptation
- Docs: https://github.com/NVIDIA/garak

---

## DeepTeam
Confident AI's framework built on DeepEval. Lowest-friction entry point: pip install, point
at an endpoint, run scans covering 40+ vulnerabilities mapped to OWASP LLM Top 10 and the
OWASP Top 10 for Agentic Applications. Integrates into standard unit-testing workflows.

Install and run:

```bash
pip install deepteam
```

```python
from deepteam import red_team
from deepteam.vulnerabilities import Bias, PIILeakage
from deepteam.attacks.single_turn import PromptInjection

def model_callback(input: str) -> str:
    return your_model(input)   # call the target under test

red_team(
    model_callback=model_callback,
    vulnerabilities=[Bias(), PIILeakage()],
    attacks=[PromptInjection()],
)
```

- Strengths: cleanest OWASP mapping, fast setup, quantitative metrics for CI gates
- Trade-offs: smaller probe library, less sophisticated multi-turn, no native multimodal yet
- Docs: https://www.trydeepteam.com

---

## Choosing a tool

| Goal | Use |
|------|-----|
| Gate every deploy / PR in CI/CD | Promptfoo (or DeepTeam for assertion-based pass/fail) |
| Fast OWASP LLM Top 10 baseline in under an hour | DeepTeam |
| Broadest one-shot model vulnerability scan | Garak |
| Custom multi-turn / multimodal research campaign | PyRIT |
| Turn red-team runs into guardrail training data | `redteam-autoresearch` skill (+ any tool above as target driver) |

Common production pattern: Promptfoo for continuous CI/CD gating, plus Garak or PyRIT for
deep periodic audits.

---

## Standards and frameworks to map findings to
- OWASP Top 10 for LLM Applications
- OWASP Top 10 for Agentic Applications
- NIST AI Risk Management Framework (AI RMF)
- MITRE ATLAS

## Attack techniques referenced above
- **PAIR** - Prompt Automatic Iterative Refinement
- **TAP** - Tree of Attacks with Pruning
- **Crescendo** - gradual multi-turn escalation
- **Many-shot / best-of-N** - volume-based bypass
- **Rainbow Teaming / MAP-Elites** - quality-diversity search for novel attacks
- **StrongREJECT** - rigorous jailbreak-success scoring rubric

## References
- AI red teaming tools comparison (2026): https://beyondscale.tech/blog/ai-red-teaming-tools-comparison-2026
- OWASP Gen AI Red Teaming Guide: https://genai.owasp.org
