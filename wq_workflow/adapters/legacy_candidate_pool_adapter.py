from __future__ import annotations

from typing import Any

from wq_workflow.core_types import CandidateDraft


def candidate_draft_from_legacy(*args: Any, **kwargs: Any) -> CandidateDraft:
    data = dict(kwargs)
    if args and isinstance(args[0], dict):
        data.update(args[0])
    return CandidateDraft.from_dict({
        "alpha_id": data.get("alpha_id") or data.get("alpha_name") or "",
        "expression": data.get("expression") or data.get("code") or "",
        "parent_id": data.get("parent_id") or data.get("parent_alpha_id") or "",
        "source": data.get("source") or data.get("candidate_source") or "legacy",
        "template_name": data.get("template_name") or data.get("template_file") or "",
        "mutation_type": data.get("mutation_type") or "",
        "generation_metadata": data.get("generation_metadata") or data,
        "created_at": data.get("created_at") or data.get("timestamp") or "",
    })
