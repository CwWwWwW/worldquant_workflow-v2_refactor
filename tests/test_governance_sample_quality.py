from types import SimpleNamespace
from wq_workflow.governance.sample_quality import SampleQualityChecker


def test_sc_quality_blocks_invalid_ratio():
    cfg = SimpleNamespace(sc_max_invalid_sample_ratio=0.05, ml_max_invalid_sample_ratio=0.2)
    report = SampleQualityChecker(config=cfg).check('sc', [{'sample_id':'1','features':{},'label':1,'platform_sc_status':'pending','platform_sc_abs_max':2.0,'source':'x'}])
    assert not report.ok
    assert report.recommended_action == 'block_train'


def test_generic_ok_and_simulator_label_required():
    cfg = SimpleNamespace(sc_max_invalid_sample_ratio=0.05, ml_max_invalid_sample_ratio=0.2)
    assert SampleQualityChecker(config=cfg).check('generic',[{'sample_id':'1','features':{},'label':1,'source':'x'}]).ok
    assert not SampleQualityChecker(config=cfg).check('simulator',[{'sample_id':'1','features':{},'label':1,'source':'x'}]).ok
