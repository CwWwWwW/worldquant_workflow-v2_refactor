from __future__ import annotations

from typing import Any


def evolution_authority(config: Any | None = None, component: str = "", *, active_decision: bool = False) -> dict[str, Any]:
    """Return consistent authority metadata for sidecar GA/RL events.

    The component argument is intentionally informational and kept in raw payloads
    only; old callers may omit config, in which case we preserve observer-only
    behavior for pure annotations.
    """
    if config is not None and not bool(getattr(config, "enable_sidecar_evolution", True)):
        return {
            "authority": "disabled",
            "decision_authority": "none",
            "experimental_enabled": False,
            "component": component,
        }
    experimental = bool(getattr(config, "enable_experimental_evolution_decisions", False)) if config is not None else False
    if active_decision and experimental:
        return {
            "authority": "experimental_decision",
            "decision_authority": "ga_rl_policy",
            "experimental_enabled": True,
            "component": component,
        }
    if active_decision:
        return {
            "authority": "advisory_only",
            "decision_authority": "none",
            "experimental_enabled": experimental,
            "component": component,
        }
    return {
        "authority": "observer_only",
        "decision_authority": "none",
        "experimental_enabled": experimental,
        "component": component,
    }
