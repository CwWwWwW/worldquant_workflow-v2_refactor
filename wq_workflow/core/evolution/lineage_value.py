from __future__ import annotations

from typing import Any

from ...safe_io import finite_float


class LineageValueEstimator:
    def __init__(self, repository: Any | None = None, config: Any | None = None) -> None:
        self.repository = repository
        self.config = config

    def estimate_future_reward(self, alpha_id: str, lineage_history: list[dict[str, Any]] | None) -> float:
        if not alpha_id:
            return 0.0
        rows = lineage_history or []
        children: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            parent_id = str(row.get("parent_id") or "")
            if parent_id:
                children.setdefault(parent_id, []).append(row)

        descendants = _descendants(alpha_id, children)
        rewards = [finite_float(row.get("reward")) for row in descendants if isinstance(row, dict)]
        if not rewards:
            return 0.0
        return round(sum(rewards) / len(rewards), 6)

    def estimate_and_update(self, alpha_id: str) -> dict[str, Any]:
        if self.repository is None or not alpha_id:
            return {}
        lookahead = int(getattr(self.config, "lineage_value_lookahead", 3) or 3)
        decay = finite_float(getattr(self.config, "lineage_value_decay", 0.75), 0.75, minimum=0.0, maximum=1.0)
        try:
            population = self.repository.list_population(limit=5000, active_only=False)
        except Exception:
            return {}
        by_id = {str(row.get("alpha_id") or ""): row for row in population}
        current = by_id.get(alpha_id, {})
        current_reward = finite_float(current.get("reward"), 0.0)
        pending: list[tuple[str, int]] = [(alpha_id, 0)]
        seen = {alpha_id}
        weighted = 0.0
        weight_sum = 0.0
        descendant_count = 0
        while pending:
            parent, depth = pending.pop(0)
            if depth >= lookahead:
                continue
            for row in population:
                child_id = str(row.get("alpha_id") or "")
                if not child_id or child_id in seen:
                    continue
                parent_ids = row.get("parent_ids") if isinstance(row.get("parent_ids"), list) else []
                if parent not in {str(item) for item in parent_ids}:
                    continue
                seen.add(child_id)
                next_depth = depth + 1
                reward = finite_float(row.get("reward"), 0.0)
                weight = decay**next_depth
                weighted += reward * weight
                weight_sum += weight
                descendant_count += 1
                pending.append((child_id, next_depth))
        future_reward = weighted / weight_sum if weight_sum else 0.0
        long_term_value = 0.5 * current_reward + 0.5 * future_reward
        payload = {
            "alpha_id": alpha_id,
            "current_reward": round(current_reward, 6),
            "future_reward": round(future_reward, 6),
            "long_term_value": round(long_term_value, 6),
            "descendant_count": descendant_count,
            "lookahead": lookahead,
        }
        self.repository.upsert_lineage_value(alpha_id, payload)
        return payload

    def estimate_population_values(self) -> list[dict[str, Any]]:
        if self.repository is None:
            return []
        try:
            population = self.repository.list_population(limit=5000, active_only=False)
        except Exception:
            return []
        result: list[dict[str, Any]] = []
        for row in population:
            payload = self.estimate_and_update(str(row.get("alpha_id") or ""))
            if payload:
                result.append(payload)
        return result


def _descendants(alpha_id: str, children: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    pending = list(children.get(alpha_id, []))
    result: list[dict[str, Any]] = []
    while pending:
        row = pending.pop(0)
        child_id = str(row.get("alpha_id") or "")
        if child_id and child_id in seen:
            continue
        if child_id:
            seen.add(child_id)
        result.append(row)
        pending.extend(children.get(child_id, []))
    return result
