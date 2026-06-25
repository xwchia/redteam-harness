"""
Shared building blocks for the red-team campaign toolkit adapters.

Every optional toolkit adapter (PyRIT, garak, promptfoo, ...) imports from this package
so that, regardless of which external tool drove the attacks, the artifacts written to
disk are byte-for-byte the same shape:

    redteam/campaigns/<run_id>/
        config.json          run metadata
        results.csv          operational steering table
        raw/<attempt>.json   full per-attempt transcript
        judged.jsonl         labeled records consumed by redteam-consolidate / -report

Modules:
    schema      Canonical field lists, the CampaignWriter, and outcome labeling.
    scoring     The rule-based heuristic scorer with all SKILL.md scoring guards.
    targets     OpenAI-compatible / Azure target bridge (reasoning-channel aware).
    techniques  The parameterized technique registry shared across adapters.
"""
