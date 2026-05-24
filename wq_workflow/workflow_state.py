from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from . import watchdog
from .logger_state import (
    STATE_ENTER,
    STATE_EXIT,
    STATE_FATAL,
    STATE_RECOVER,
    STATE_RETRY,
    STATE_TIMEOUT,
    log_state_event,
)
from .recovery import RecoveryLevel


class WorkflowState(Enum):
    INIT = auto()
    AUTH_CHECK = auto()
    OPEN_SIMULATE = auto()
    EDITOR_READY = auto()
    WRITE_CODE = auto()
    WRITE_NAME = auto()
    CLICK_RUN = auto()
    WAIT_QUEUE = auto()
    WAIT_RESULT = auto()
    PARSE_RESULT = auto()
    QUALITY_CHECK = auto()
    ADD_FAVORITE = auto()
    FINISHED = auto()

    RECOVER_PAGE = auto()
    REBUILD_CONTEXT = auto()
    RESTART_BROWSER = auto()
    RESTART_TASK = auto()
    FATAL_ERROR = auto()


@dataclass(frozen=True)
class StatePolicy:
    timeout: float
    max_retry: int
    recovery: WorkflowState
    recovery_level: RecoveryLevel


STATE_POLICIES: dict[WorkflowState, StatePolicy] = {
    WorkflowState.INIT: StatePolicy(10, 0, WorkflowState.RESTART_BROWSER, RecoveryLevel.LEVEL_4_RESTART_BROWSER),
    WorkflowState.AUTH_CHECK: StatePolicy(120, 1, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.OPEN_SIMULATE: StatePolicy(90, 1, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.EDITOR_READY: StatePolicy(150, 1, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.WRITE_CODE: StatePolicy(90, 1, WorkflowState.RECOVER_PAGE, RecoveryLevel.LEVEL_1_RELOAD_PAGE),
    WorkflowState.WRITE_NAME: StatePolicy(60, 1, WorkflowState.RECOVER_PAGE, RecoveryLevel.LEVEL_1_RELOAD_PAGE),
    WorkflowState.CLICK_RUN: StatePolicy(45, 1, WorkflowState.RECOVER_PAGE, RecoveryLevel.LEVEL_1_RELOAD_PAGE),
    WorkflowState.WAIT_QUEUE: StatePolicy(60, 1, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.WAIT_RESULT: StatePolicy(300, 2, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.PARSE_RESULT: StatePolicy(60, 1, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.QUALITY_CHECK: StatePolicy(30, 0, WorkflowState.RESTART_TASK, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.ADD_FAVORITE: StatePolicy(90, 1, WorkflowState.REBUILD_CONTEXT, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT),
    WorkflowState.FINISHED: StatePolicy(10, 0, WorkflowState.RESTART_BROWSER, RecoveryLevel.LEVEL_4_RESTART_BROWSER),
}


STATE_ORDER = [
    WorkflowState.INIT,
    WorkflowState.AUTH_CHECK,
    WorkflowState.OPEN_SIMULATE,
    WorkflowState.EDITOR_READY,
    WorkflowState.WRITE_CODE,
    WorkflowState.WRITE_NAME,
    WorkflowState.CLICK_RUN,
    WorkflowState.WAIT_QUEUE,
    WorkflowState.WAIT_RESULT,
    WorkflowState.PARSE_RESULT,
    WorkflowState.QUALITY_CHECK,
    WorkflowState.ADD_FAVORITE,
    WorkflowState.FINISHED,
]


class WorkflowStateError(RuntimeError):
    def __init__(
        self,
        state: WorkflowState,
        message: str,
        *,
        recovery_state: WorkflowState,
        recovery_level: RecoveryLevel,
        retry: int,
        nonrecoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.state = state
        self.recovery_state = recovery_state
        self.recovery_level = recovery_level
        self.retry = retry
        self.nonrecoverable = nonrecoverable


class NonRecoverableStateError(RuntimeError):
    pass


StateHandler = Callable[[], Awaitable[Any]]
RecoverHandler = Callable[[WorkflowState, StatePolicy, BaseException, int], Awaitable[None]]


class WorkflowFSM:
    def __init__(
        self,
        *,
        alpha_id: str,
        handlers: dict[WorkflowState, StateHandler],
        recover: RecoverHandler | None = None,
    ) -> None:
        self.alpha_id = alpha_id
        self.handlers = handlers
        self.recover = recover
        self.trace: list[dict[str, Any]] = []

    async def run(self) -> list[dict[str, Any]]:
        for state in STATE_ORDER:
            await self._run_state(state)
        return self.trace

    async def _run_state(self, state: WorkflowState) -> None:
        policy = STATE_POLICIES[state]
        retry = 0
        while True:
            started = time.monotonic()
            log_state_event(STATE_ENTER, alpha_id=self.alpha_id, state=state.name, retry=retry)
            try:
                handler = self.handlers.get(state)
                if handler:
                    await watchdog.step(f"{self.alpha_id}:{state.name}", handler(), policy.timeout)
                duration = time.monotonic() - started
                event = log_state_event(
                    STATE_EXIT,
                    alpha_id=self.alpha_id,
                    state=state.name,
                    duration=duration,
                    retry=retry,
                )
                self.trace.append(event)
                return
            except watchdog.WatchdogTimeout as exc:
                duration = time.monotonic() - started
                log_state_event(
                    STATE_TIMEOUT,
                    alpha_id=self.alpha_id,
                    state=state.name,
                    duration=duration,
                    retry=retry,
                    recovery=policy.recovery.name,
                    error=str(exc),
                )
                if retry < policy.max_retry:
                    retry += 1
                    await self._recover(state, policy, exc, retry)
                    continue
                await self._fatal(state, policy, exc, retry)
            except NonRecoverableStateError as exc:
                duration = time.monotonic() - started
                log_state_event(
                    STATE_FATAL,
                    alpha_id=self.alpha_id,
                    state=state.name,
                    duration=duration,
                    retry=retry,
                    recovery=WorkflowState.RESTART_TASK.name,
                    error=str(exc),
                )
                raise WorkflowStateError(
                    state,
                    str(exc),
                    recovery_state=WorkflowState.RESTART_TASK,
                    recovery_level=RecoveryLevel.LEVEL_3_REBUILD_CONTEXT,
                    retry=retry,
                    nonrecoverable=True,
                ) from exc
            except Exception as exc:
                duration = time.monotonic() - started
                log_state_event(
                    STATE_RETRY if retry < policy.max_retry else STATE_FATAL,
                    alpha_id=self.alpha_id,
                    state=state.name,
                    duration=duration,
                    retry=retry,
                    recovery=policy.recovery.name,
                    error=str(exc),
                )
                if retry < policy.max_retry:
                    retry += 1
                    await self._recover(state, policy, exc, retry)
                    continue
                await self._fatal(state, policy, exc, retry)

    async def _recover(self, state: WorkflowState, policy: StatePolicy, exc: BaseException, retry: int) -> None:
        log_state_event(
            STATE_RECOVER,
            alpha_id=self.alpha_id,
            state=policy.recovery.name,
            retry=retry,
            recovery=policy.recovery_level.name,
            error=str(exc),
        )
        if self.recover:
            await self.recover(state, policy, exc, retry)

    async def _fatal(self, state: WorkflowState, policy: StatePolicy, exc: BaseException, retry: int) -> None:
        log_state_event(
            STATE_FATAL,
            alpha_id=self.alpha_id,
            state=WorkflowState.FATAL_ERROR.name,
            retry=retry,
            recovery=policy.recovery_level.name,
            error=str(exc),
        )
        raise WorkflowStateError(
            state,
            str(exc),
            recovery_state=policy.recovery,
            recovery_level=policy.recovery_level,
            retry=retry,
        ) from exc
