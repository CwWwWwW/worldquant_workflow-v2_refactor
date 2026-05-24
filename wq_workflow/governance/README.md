# Long-Term Learning Governance Layer

This package is an independent governance sub-layer for autonomous learning models.

Boundaries:

- It may read model registry metadata, online evaluation data, sample quality data, and runtime status.
- It may disable model hard-decision eligibility, reduce model weight, request retraining, roll back registry pointers, and write audit/status records.
- It must not directly operate Playwright, browser/page objects, platform automation, reward semantics, or alpha generation.
- All failures are non-fatal and must fall back to legacy behavior.

Default policy:

- New models start as `candidate` or `shadow`.
- Hard decisions require `limited_active` or `champion` plus online/sample/registry safety checks.
- SC, Parent, Policy, Simulator, Outcome, and Insight are governed through `LearningGovernanceService` and `GovernancePolicyGate`.
