"""
Optional toolkit adapters for the red-team campaign skill.

Each adapter drives its tool's attack machinery while routing all output through
lib.schema.CampaignWriter, guaranteeing that the artifacts it produces are identical
to those from the reference runner (run_campaign.py) and are consumable by
redteam-consolidate and redteam-report without modification.

Adapters:
    pyrit_adapter.py      PyRIT single-turn sweep + Crescendo multi-turn orchestrator.
    garak_adapter.py      garak scan wrapper: runs a probe sweep and converts the HTML/JSON
                          report into the canonical judged.jsonl format.
    promptfoo_adapter.py  promptfoo config generator + eval runner + result converter.

Install the required packages before using each adapter (see toolkits/README.md).
"""
