from pathlib import Path
from wq_workflow.models import WorkflowConfig


def test_counterfactual_boundaries_static():
    files=list(Path('wq_workflow/offline').glob('counterfactual*.py'))
    text='\n'.join(p.read_text(encoding='utf-8') for p in files)
    forbidden=['playwright','browser.new_page','CandidatePool','submit_backtest','hard_takeover','decision_outcomes SET','offline_replay_policy_decisions SET reward']
    for item in forbidden:
        assert item not in text
    assert WorkflowConfig().enable_counterfactual_evaluation is False
    assert WorkflowConfig().counterfactual_auto_run is False
