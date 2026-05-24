from .schema import DecisionAction, DecisionOutcome, DecisionSnapshot, DecisionSnapshotSummary
from .decision_snapshot import DecisionOutcomeRecorder, DecisionSnapshotBuilder, DecisionSnapshotLogger
from .repository import DecisionSnapshotRepository
from .reporter import DecisionSnapshotReporter
from .service import DecisionSnapshotService

try:  # Existing Phase 4/strategy imports are kept for compatibility only.
    from .counterfactual import CounterfactualEstimator
    from .replay import OfflineReplayEvaluator
    from .support_checker import SupportChecker
except Exception:  # pragma: no cover - fail-open optional services
    CounterfactualEstimator = None  # type: ignore[assignment]
    OfflineReplayEvaluator = None  # type: ignore[assignment]
    SupportChecker = None  # type: ignore[assignment]

__all__ = [
    "DecisionAction",
    "DecisionOutcome",
    "DecisionSnapshot",
    "DecisionSnapshotSummary",
    "DecisionSnapshotBuilder",
    "DecisionSnapshotLogger",
    "DecisionOutcomeRecorder",
    "DecisionSnapshotRepository",
    "DecisionSnapshotReporter",
    "DecisionSnapshotService",
    "CounterfactualEstimator",
    "OfflineReplayEvaluator",
    "SupportChecker",
]
