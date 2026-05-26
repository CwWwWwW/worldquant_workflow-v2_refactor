from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .evidence import LegacyLearningEvidenceBuilder, LegacyLearningEvidenceWriter
from .recent_events import RecentEventWriter
from .runtime_state import RuntimeStateWriter
from .schema import RuntimeEvent
from .utils import summarize_exception, summarize_payload, truncate_text, utc_now_iso


class LegacyIterationObserver:
    def __init__(
        self,
        *,
        config: Any | None = None,
        root: str | Path | None = None,
        runtime_state_path: str | Path | None = None,
        recent_events_path: str | Path | None = None,
        learning_evidence_path: str | Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.config = config
        self.root = Path(root or paths.ROOT)
        self.enabled = bool(enabled)
        self.max_message_chars = int(getattr(config, "legacy_observer_max_message_chars", 300) or 300)
        self.max_payload_chars = int(getattr(config, "legacy_observer_max_event_payload_chars", 1000) or 1000)
        self.include_traceback = bool(getattr(config, "legacy_observer_include_traceback", False))
        self.state_writer = RuntimeStateWriter(
            runtime_state_path or getattr(config, "legacy_runtime_state_path", "runtime/status/runtime_state.json"),
            root=self.root,
            enabled=bool(getattr(config, "legacy_observer_write_runtime_state", True)),
        )
        self.event_writer = RecentEventWriter(
            recent_events_path or getattr(config, "legacy_recent_events_path", "runtime/status/recent_events.jsonl"),
            root=self.root,
            enabled=bool(getattr(config, "legacy_observer_write_recent_events", True)),
            max_bytes=int(getattr(config, "legacy_recent_events_max_bytes", 5_242_880) or 5_242_880),
        )
        self.evidence_writer = LegacyLearningEvidenceWriter(
            learning_evidence_path or getattr(config, "legacy_learning_evidence_path", "runtime/status/legacy_learning_evidence.jsonl"),
            root=self.root,
            enabled=bool(getattr(config, "legacy_observer_write_learning_evidence", True)),
            max_bytes=int(getattr(config, "legacy_learning_evidence_max_bytes", 10_485_760) or 10_485_760),
        )
        self.evidence_builder = LegacyLearningEvidenceBuilder()
        self._last_status: dict[str, Any] = {"enabled": self.enabled}

    def get_status(self) -> dict[str, Any]:
        return dict(self._last_status)

    def _event(self, event_type: str, *, state: str | None = None, severity: str = "info", message: str = "", evidence_type: str | None = None, state_updates: dict[str, Any] | None = None, evidence_kwargs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if not self.enabled:
            return
        try:
            now = utc_now_iso()
            payload = summarize_payload(kwargs.get("raw_payload") or kwargs.get("payload") or kwargs, max_payload_chars=self.max_payload_chars, max_text_chars=self.max_message_chars)
            alpha_id = kwargs.get("alpha_id")
            iteration = kwargs.get("iteration")
            template_name = kwargs.get("template_name") or kwargs.get("current_template")
            template_family = kwargs.get("template_family") or kwargs.get("current_template_family")
            event = RuntimeEvent(
                timestamp=now,
                event_type=event_type,
                state=state,
                alpha_id=str(alpha_id) if alpha_id not in (None, "") else None,
                iteration=iteration,
                template_name=str(template_name) if template_name not in (None, "") else None,
                template_family=str(template_family) if template_family not in (None, "") else None,
                message=truncate_text(message or event_type, self.max_message_chars),
                severity=severity,
                reason_codes=[str(item) for item in (kwargs.get("reason_codes") or [])],
                payload_summary=payload,
                raw_payload=payload,
            )
            self.event_writer.append_event(event)
            updates = {
                "last_event_at": now,
                "current_state": state,
                "current_alpha_id": event.alpha_id,
                "current_iteration": event.iteration,
                "current_template": event.template_name,
                "current_template_family": event.template_family,
                "raw_payload": payload,
            }
            updates.update(state_updates or {})
            self.state_writer.write_fail_open({key: value for key, value in updates.items() if value is not None})
            if evidence_type:
                method = getattr(self.evidence_builder, f"from_{evidence_type}", None)
                builder_kwargs = {
                    "alpha_id": event.alpha_id,
                    "iteration": event.iteration,
                    "template_name": event.template_name,
                    "template_family": event.template_family,
                    "raw_payload": payload,
                    **(evidence_kwargs or {}),
                }
                evidence = method(**builder_kwargs) if callable(method) else self.evidence_builder.build_generic(evidence_type, **builder_kwargs)
                self.evidence_writer.append_evidence(evidence)
            self._last_status = {"enabled": True, "last_event_type": event_type, "last_state": state, "last_event_at": now}
        except Exception as exc:
            self._last_status = {"enabled": self.enabled, "last_error": summarize_exception(exc)}
            if not bool(getattr(self.config, "legacy_observer_fail_open", True)):
                raise

    def on_workflow_start(self, **kwargs: Any) -> None:
        self._event("WORKFLOW_START", state="STARTING", message="legacy workflow start", state_updates={"workflow_running": True}, **kwargs)

    def on_template_selected(self, **kwargs: Any) -> None:
        self._event("TEMPLATE_SELECTED", state="TEMPLATE_SELECTED", message="template selected", evidence_type="template_selected", **kwargs)

    def on_alpha_generated(self, **kwargs: Any) -> None:
        self._event("ALPHA_GENERATED", state="ALPHA_GENERATED", message="alpha generated", evidence_type="alpha_generated", **kwargs)

    def on_backtest_submit_start(self, **kwargs: Any) -> None:
        self._event("BACKTEST_SUBMIT_START", state="SUBMITTING_BACKTEST", message="backtest submit start", evidence_type="backtest_submitted", state_updates={"platform_waiting": True}, **kwargs)

    def on_backtest_submit_done(self, **kwargs: Any) -> None:
        self._event("BACKTEST_SUBMIT_DONE", state="SUBMITTING_BACKTEST", message="backtest submit done", **kwargs)

    def on_wait_result_start(self, **kwargs: Any) -> None:
        self._event("WAIT_RESULT_START", state="WAIT_RESULT", message="wait result start", state_updates={"platform_waiting": True}, **kwargs)

    def on_wait_result_progress(self, **kwargs: Any) -> None:
        self._event("WAIT_RESULT_PROGRESS", state="WAIT_RESULT", severity="debug", message="wait result progress", state_updates={"platform_waiting": True, "platform_progress": kwargs.get("platform_progress") or kwargs.get("progress")}, **kwargs)

    def on_wait_result_done(self, **kwargs: Any) -> None:
        self._event("WAIT_RESULT_DONE", state="WAIT_RESULT", message="wait result done", state_updates={"platform_waiting": False, "platform_progress": kwargs.get("platform_progress") or kwargs.get("progress")}, **kwargs)

    def on_parse_result_start(self, **kwargs: Any) -> None:
        self._event("PARSE_RESULT_START", state="PARSE_RESULT", message="parse result start", state_updates={"parse_waiting": True, "parse_status": "running"}, **kwargs)

    def on_parse_result_done(self, **kwargs: Any) -> None:
        self._event("PARSE_RESULT_DONE", state="PARSE_RESULT", message="parse result done", evidence_type="parse_result", state_updates={"parse_waiting": False, "parse_status": kwargs.get("parse_status") or "done", "last_result_status": kwargs.get("result_status")}, evidence_kwargs={"metrics": kwargs.get("metrics") or {}, "result_status": kwargs.get("result_status")}, **kwargs)

    def on_sc_check_start(self, **kwargs: Any) -> None:
        self._event("PLATFORM_SC_CHECK_START", state="PLATFORM_SC_CHECK", message="platform sc check start", state_updates={"sc_check_status": "running"}, **kwargs)

    def on_sc_check_done(self, **kwargs: Any) -> None:
        platform_sc = kwargs.get("platform_sc") if isinstance(kwargs.get("platform_sc"), dict) else {}
        sc_value = kwargs.get("sc_value") or platform_sc.get("abs_max") or platform_sc.get("max")
        self._event("PLATFORM_SC_CHECK_DONE", state="PLATFORM_SC_CHECK", message="platform sc check done", evidence_type="sc_check", state_updates={"sc_check_status": platform_sc.get("status") or kwargs.get("sc_check_status") or "done", "last_sc_value": sc_value}, evidence_kwargs={"platform_sc": platform_sc, "sc_value": sc_value, "result_status": platform_sc.get("status")}, **kwargs)

    def on_governance_check_start(self, **kwargs: Any) -> None:
        self._event("GOVERNANCE_CHECK_START", state="GOVERNANCE_CHECK", message="governance check start", **kwargs)

    def on_governance_check_done(self, **kwargs: Any) -> None:
        self._event("GOVERNANCE_CHECK_DONE", state="GOVERNANCE_CHECK", message="governance check done", evidence_type="governance_result", state_updates={"governance_summary": summarize_payload(kwargs)}, **kwargs)

    def on_reward_update(self, **kwargs: Any) -> None:
        self._event("REWARD_UPDATE", state="REWARD_UPDATE", message="reward update", evidence_type="reward_update", state_updates={"last_reward": kwargs.get("reward")}, evidence_kwargs={"reward": kwargs.get("reward"), "metrics": kwargs.get("metrics") or {}, "platform_sc": kwargs.get("platform_sc") or {}}, **kwargs)

    def on_candidate_pool_update(self, **kwargs: Any) -> None:
        self._event("CANDIDATE_POOL_UPDATE", state="CANDIDATE_POOL_UPDATE", message="candidate pool update", evidence_type="candidate_pool_update", **kwargs)

    def on_observability_snapshot(self, **kwargs: Any) -> None:
        self._event("OBSERVABILITY_SNAPSHOT", state="OBSERVABILITY_READY", message="observability snapshot", state_updates={"observability_summary": summarize_payload(kwargs)}, **kwargs)

    def on_recoverable_error(self, error: Exception | str | None = None, **kwargs: Any) -> None:
        raw_message = kwargs.pop("message", None)
        message = summarize_exception(error or raw_message or "recoverable error", include_traceback=self.include_traceback, max_chars=self.max_message_chars)
        self._event("RECOVERABLE_ERROR", state="ERROR_RECOVERABLE", severity="error", message=message, evidence_type="failure", state_updates={"last_error_summary": message}, evidence_kwargs={"failure_reason": message, "result_status": "recoverable_error"}, **kwargs)

    def on_fatal_error(self, error: Exception | str | None = None, **kwargs: Any) -> None:
        raw_message = kwargs.pop("message", None)
        message = summarize_exception(error or raw_message or "fatal error", include_traceback=self.include_traceback, max_chars=self.max_message_chars)
        self._event("FATAL_ERROR", state="ERROR_FATAL", severity="critical", message=message, evidence_type="failure", state_updates={"workflow_running": False, "last_error_summary": message}, evidence_kwargs={"failure_reason": message, "result_status": "fatal_error"}, **kwargs)

    def on_workflow_stop(self, **kwargs: Any) -> None:
        self._event("WORKFLOW_STOP", state="IDLE", message="legacy workflow stop", state_updates={"workflow_running": False, "platform_waiting": False, "parse_waiting": False}, **kwargs)
