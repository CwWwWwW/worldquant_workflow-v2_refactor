from wq_workflow.app.self_healing import SelfHealingGuard


class Gov:
    def __init__(self): self.called=False
    def handle_prediction_error(self,*a): self.called=True
    def handle_model_load_error(self,*a): self.called=True


def test_self_healing_notifies_governance():
    g=Gov(); h=SelfHealingGuard(governance_service=g)
    assert h.safe_call('sc_predict', lambda: (_ for _ in ()).throw(RuntimeError('x')), fallback='f') == 'f'
    assert g.called
