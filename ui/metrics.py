from __future__ import annotations

from typing import Any

from wq_workflow.safe_io import finite_float

from .models import PopulationMetrics


def population_metrics(pool_rows: list[dict[str, Any]], lineage_rows: list[dict[str, Any]]) -> PopulationMetrics:
    pool = pool_rows if isinstance(pool_rows, list) else []
    lineage = lineage_rows if isinstance(lineage_rows, list) else []
    recent_lineage = lineage[-80:]

    diversity = _avg([_float(row.get("diversity_score"), 1.0) for row in pool if "diversity_score" in row], 0.0)
    correlation_values = []
    for row in pool:
        if "estimated_self_corr" in row:
            correlation_values.append(_float(row.get("estimated_self_corr")))
        elif "max_semantic_similarity" in row:
            correlation_values.append(_float(row.get("max_semantic_similarity")))
        elif "structural_correlation" in row:
            correlation_values.append(_float(row.get("structural_correlation")))
        elif "return_correlation" in row:
            correlation_values.append(_float(row.get("return_correlation")))
    correlation = _avg(correlation_values, max(0.0, 1.0 - diversity) if pool else 0.0)

    successes = sum(1 for row in recent_lineage if row.get("passed") or _float(row.get("reward")) > 0)
    mutation_success_rate = successes / len(recent_lineage) if recent_lineage else 0.0

    reward_values = [_float(row.get("reward")) for row in recent_lineage if "reward" in row]
    reward_stability = _variance(reward_values)

    survived = sum(1 for row in pool if row.get("passed") or _float(row.get("reward")) > 0)
    survival_rate = survived / len(pool) if pool else 0.0

    return PopulationMetrics(
        count=len(pool),
        diversity=round(diversity, 6),
        correlation=round(correlation, 6),
        mutation_success_rate=round(mutation_success_rate, 6),
        reward_stability=round(reward_stability, 6),
        survival_rate=round(survival_rate, 6),
    )


def pass_rate_from_rows(pool_rows: list[dict[str, Any]], lineage_rows: list[dict[str, Any]]) -> float:
    rows = lineage_rows[-80:] if lineage_rows else pool_rows
    if not rows:
        return 0.0
    passed = sum(1 for row in rows if row.get("passed") or row.get("template_success"))
    return round(passed / len(rows), 6)


def queue_size_from_workers(workers: list[Any]) -> int:
    return sum(1 for worker in workers if getattr(worker, "current_task", "") == "WAIT_QUEUE")


def _avg(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


def _variance(values: list[float]) -> float:
    values = [finite_float(value) for value in values]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _float(value: Any, default: float = 0.0) -> float:
    return finite_float(value, default)
