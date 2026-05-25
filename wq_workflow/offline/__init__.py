from .schema import (
    DecisionAction,
    DecisionOutcome,
    DecisionSnapshot,
    DecisionSnapshotSummary,
    CounterfactualEstimate,
    CounterfactualEvidence,
    CounterfactualRequest,
    CounterfactualSummary,
    ReplayComparison,
    ReplayDatasetFilter,
    ReplayPolicyDecision,
    ReplayPolicyMetrics,
    ReplayRecord,
    ReplayRun,
)
from .decision_snapshot import DecisionOutcomeRecorder, DecisionSnapshotBuilder, DecisionSnapshotLogger
from .repository import DecisionSnapshotRepository
from .reporter import DecisionSnapshotReporter
from .counterfactual_dataset import CounterfactualDatasetLoader
from .counterfactual_evaluator import CounterfactualEvaluator
from .counterfactual_features import CounterfactualFeatureBuilder
from .counterfactual_metrics import CounterfactualMetricsCalculator
from .counterfactual_neighbors import CounterfactualNeighborIndex
from .counterfactual_repository import CounterfactualRepository
from .counterfactual_reporter import CounterfactualReporter
from .replay_dataset import ReplayDatasetLoader
from .replay_engine import ReplayEngine
from .replay_policy import ActualChosenReplayPolicy, BudgetChoiceReplayPolicy, ExperimentChoiceReplayPolicy, LegacyReplayPolicy, ModelChoiceReplayPolicy, ReplayPolicy
from .replay_repository import ReplayRepository
from .replay_reporter import ReplayReporter
from .service import CounterfactualService, DecisionSnapshotService, OfflineReplayService

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
    "CounterfactualEstimate",
    "CounterfactualEvidence",
    "CounterfactualRequest",
    "CounterfactualSummary",
    "ReplayComparison",
    "ReplayDatasetFilter",
    "ReplayPolicyDecision",
    "ReplayPolicyMetrics",
    "ReplayRecord",
    "ReplayRun",
    "DecisionSnapshotBuilder",
    "DecisionSnapshotLogger",
    "DecisionOutcomeRecorder",
    "DecisionSnapshotRepository",
    "DecisionSnapshotReporter",
    "DecisionSnapshotService",
    "CounterfactualDatasetLoader",
    "CounterfactualEvaluator",
    "CounterfactualFeatureBuilder",
    "CounterfactualMetricsCalculator",
    "CounterfactualNeighborIndex",
    "CounterfactualRepository",
    "CounterfactualReporter",
    "CounterfactualService",
    "ReplayDatasetLoader",
    "ReplayEngine",
    "ReplayPolicy",
    "ActualChosenReplayPolicy",
    "LegacyReplayPolicy",
    "ModelChoiceReplayPolicy",
    "ExperimentChoiceReplayPolicy",
    "BudgetChoiceReplayPolicy",
    "ReplayRepository",
    "ReplayReporter",
    "OfflineReplayService",
    "CounterfactualEstimator",
    "OfflineReplayEvaluator",
    "SupportChecker",
]
