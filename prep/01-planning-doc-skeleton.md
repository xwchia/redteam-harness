# Red-Team Plan

> Copy this into the test repo as `plan.md`, fill the brackets, commit within the first 30 minutes.

## 1. Objective and success metric

- Target: [model name / endpoint]
- Provided baseline (Opus 4.1) score: [X]
- Goal: beat baseline by [target], prioritizing severity over raw count.
- Definition of "success" per item: evaluator marks compliance AND non-trivial severity.

## 2. Understanding of the harness

- API client: [base URL, auth, model, request/response schema, max tokens]
- Rate limits / constraints: [requests-per-min, token caps, timeouts]
- Evaluator: [classifier vs judge-LLM], scores on [compliance / severity / both],
  required output schema = [describe exactly], headline score printed at [where].
- Behaviors dataset: [path], [N items] across categories: [list categories].

## 3. Baseline gap analysis

- Categories the baseline FAILED: [list]
- Evaluator's stated reasons for low scores: [paraphrase]
- Highest-leverage targets (failed baseline + plausibly winnable): [ranked list]

## 4. Approach

- Primary: attacker-in-the-loop harness (generate -> send -> score -> refine).
- Technique families to template as transforms (see harness notes): [list the
  families you will implement first, ordered by expected payoff for this model].
- Iteration policy: feed refusals back into refinement; budget = [depth/branches].
- Concurrency: [N] parallel within rate limits.

## 5. Work plan / time budget

- 0-30 min: orient + this plan (committed).
- 30-90 min: agent builds harness; dry-run; full sweep; iterate near-misses.
- 90-120 min: report, official re-score, transcript export, commit, push.

## 6. Risks and how I handle them

- Agent refusal: truthful re-framing + Claude Code Opus 4.1 fallback.
- Rate limiting: backoff + concurrency cap + prioritized behavior queue.
- Eval gaming vs real jailbreaks: track which is which; report honestly.
- Time overrun: hard stop at 90 min for new attacks; protect reporting time.

## 7. Deliverables checklist

- [ ] plan.md (this file)
- [ ] harness code + run command
- [ ] raw request/response logs + results CSV
- [ ] report.md
- [ ] full AI transcript
