from __future__ import annotations

from typing import Any


class SuccessDetector:
    def detect_template_success(self, *args: Any, **kwargs: Any) -> Any:
        from wq_workflow.template_success_detector import detect_template_success

        return detect_template_success(*args, **kwargs)

    def detect_favorite_success(self, payload: Any) -> bool:
        data = payload if isinstance(payload, dict) else getattr(payload, "__dict__", {})
        return bool(data.get("favorite_added") or data.get("favorited") or data.get("success"))

    def detect_backtest_success(self, simulation_result: Any) -> bool:
        data = simulation_result.to_dict() if hasattr(simulation_result, "to_dict") else (simulation_result if isinstance(simulation_result, dict) else getattr(simulation_result, "__dict__", {}))
        return bool(data.get("ok") or data.get("passed") or data.get("success"))
