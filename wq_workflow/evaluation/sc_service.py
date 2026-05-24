from __future__ import annotations

from typing import Any

from wq_workflow.core_types import ServiceResult


class SCService:
    def resolve(self, platform_sc: Any = None, local_sc: Any = None, learned_sc: Any = None) -> ServiceResult[dict[str, Any]]:
        platform_payload = _payload(platform_sc)
        if platform_payload.get("status") == "complete":
            return ServiceResult(ok=True, data=platform_payload, source="platform_sc", raw_payload={"platform_sc": platform_payload})
        local_payload = _payload(local_sc)
        if local_payload:
            return ServiceResult(ok=True, data=local_payload, source="local_sc", raw_payload={"platform_sc": platform_payload, "local_sc": local_payload})
        learned_payload = _payload(learned_sc)
        if learned_payload:
            return ServiceResult(ok=False, data=learned_payload, warnings=["learned_sc_observe_only"], source="learned_sc_observe_only", raw_payload={"learned_sc": learned_payload})
        return ServiceResult(ok=False, data={}, error="no_sc_available", source="sc_service")


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_payload"):
        return value.to_payload()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(value) if isinstance(value, dict) else {}
