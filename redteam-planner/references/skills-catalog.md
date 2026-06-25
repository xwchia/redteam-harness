# Skills catalog (distilled)

Downloadable Agent Skills useful for red-teaming AI systems. Install pattern:
`npx skills add <owner>/<repo> --skill <name> -a cursor -y`. Audit any third-party skill
with `skill-security` before trusting it.

## Targets models / LLM behavior
- `redteam-autoresearch` (superagent-ai/skills) - bounded autoresearch loop; agent is
  attacker and judge; techniques include PAIR/TAP, Crescendo, many-shot, best-of-N;
  MAP-Elites coverage; StrongREJECT judging; exports Llama Guard JSONL. Strongest model
  red-team match.
- `llm-testing` (Eyadkelleh/awesome-skills-security) - prompts for bias, PII/data leakage,
  alignment, adversarial resistance. Good seed/reference library.

## Offensive orchestration
- `hacker` (superagent-ai/skills) - instruction-only engagement orchestrator; engagement
  and validate-findings modes; scope-gated.
- `recon-security` (superagent-ai/skills) - external pentest workflow with free tools
  (subfinder, httpx, nmap, nuclei, ffuf).

## Defensive / supporting (for AI-application red-teaming and vetting)
- `skill-security` - "is this skill safe to install?" offline scanner + intent check.
- `authz-security` - IDOR/BOLA in app source.
- `crypto-secrets` - hardcoded secrets and weak crypto.
- `supply-chain-security` - malicious dependencies.
- `ci-cd-security` - GitHub Actions supply-chain bugs.
- `infra-security` - Terraform/K8s/CloudFormation/Docker misconfig.
- `vulnerability-triage` / `security-disclosure-triage` - is a report real, by-design, or noise.

## Recommended install set for model red-teaming
```bash
npx skills add superagent-ai/skills --skill skill-security -a cursor -y
npx skills add superagent-ai/skills --skill redteam-autoresearch -a cursor -y
npx skills add Eyadkelleh/awesome-skills-security --skill llm-testing -a cursor -y
```

Full source: superagent-ai/skills and Eyadkelleh/awesome-skills-security (both MIT).
