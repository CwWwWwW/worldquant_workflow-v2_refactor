from pathlib import Path


def test_governance_layer_structure():
    root = Path('wq_workflow/governance')
    assert root.exists()
    for name in ['service.py','policy_gate.py','registry_adapter.py','README.md','long_term_guard.py','sample_quality.py']:
        assert (root / name).exists()
    for bad in ['wq_workflow/platform/governance.py','wq_workflow/alpha/governance.py','wq_workflow/evaluation/governance.py','wq_workflow/data/governance.py']:
        assert not Path(bad).exists()
