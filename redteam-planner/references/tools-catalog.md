# Tools catalog (distilled)

Open-source frameworks for adversarially testing LLMs and AI applications. Authorized
targets only.

## Quick comparison
| Tool | Owner / License | Type | Multi-turn | Best for |
|------|-----------------|------|------------|----------|
| Promptfoo | OpenAI / MIT | YAML eval + red team | Yes (Hydra) | CI/CD gating for apps, RAG, agents |
| PyRIT | Microsoft / MIT | Python orchestration | Yes (Crescendo, TAP, PAIR) | Custom multi-turn / multimodal research |
| Garak | NVIDIA / Apache 2.0 | Vulnerability scanner | Limited | High-volume baseline model audits |
| DeepTeam | Confident AI / Apache 2.0 | Metric-driven eval | Yes | Fast OWASP LLM Top 10 baseline |

## Quickstarts
- Promptfoo: `npx promptfoo@latest redteam init` then `redteam run` then `redteam report`.
- PyRIT: `pip install pyrit`; use orchestrators (PromptSendingOrchestrator, CrescendoOrchestrator).
- Garak: `pip install garak`; `python -m garak --model_type openai --model_name <m> --probes all`.
- DeepTeam: `pip install deepteam`; call `red_team(model_callback, vulnerabilities, attacks)`.

## Choosing
| Goal | Use |
|------|-----|
| Gate every deploy/PR in CI | Promptfoo (or DeepTeam for pass/fail gates) |
| Fast OWASP baseline | DeepTeam |
| Broadest one-shot scan | Garak |
| Custom multi-turn/multimodal campaign | PyRIT |
| Turn runs into guardrail training data | redteam-autoresearch skill |

## Standards to map findings to
OWASP Top 10 for LLM Applications, OWASP Top 10 for Agentic Applications, NIST AI RMF, MITRE ATLAS.

## Techniques glossary
PAIR (iterative refinement), TAP (tree of attacks with pruning), Crescendo (gradual
multi-turn escalation), many-shot / best-of-N, Rainbow Teaming / MAP-Elites (quality-diversity
search), StrongREJECT (rigorous jailbreak-success scoring).
