import unittest

from wq_workflow.recovery import RecoveryLevel
from wq_workflow.workflow_state import (
    STATE_POLICIES,
    NonRecoverableStateError,
    WorkflowFSM,
    WorkflowState,
    WorkflowStateError,
)


class FsmPolicyTests(unittest.TestCase):
    def test_required_states_exist(self) -> None:
        required = {
            "INIT",
            "AUTH_CHECK",
            "OPEN_SIMULATE",
            "EDITOR_READY",
            "WRITE_CODE",
            "WRITE_NAME",
            "CLICK_RUN",
            "WAIT_QUEUE",
            "WAIT_RESULT",
            "PARSE_RESULT",
            "QUALITY_CHECK",
            "ADD_FAVORITE",
            "FINISHED",
            "RECOVER_PAGE",
            "REBUILD_CONTEXT",
            "RESTART_BROWSER",
            "RESTART_TASK",
            "FATAL_ERROR",
        }

        self.assertTrue(required.issubset({state.name for state in WorkflowState}))

    def test_wait_result_policy_rebuilds_context(self) -> None:
        policy = STATE_POLICIES[WorkflowState.WAIT_RESULT]

        self.assertEqual(policy.timeout, 300)
        self.assertEqual(policy.max_retry, 2)
        self.assertEqual(policy.recovery, WorkflowState.REBUILD_CONTEXT)
        self.assertEqual(policy.recovery_level, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT)

    def test_click_run_policy_recovers_page_first(self) -> None:
        policy = STATE_POLICIES[WorkflowState.CLICK_RUN]

        self.assertEqual(policy.timeout, 45)
        self.assertEqual(policy.max_retry, 1)
        self.assertEqual(policy.recovery, WorkflowState.RECOVER_PAGE)
        self.assertEqual(policy.recovery_level, RecoveryLevel.LEVEL_1_RELOAD_PAGE)


class FsmExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonrecoverable_state_error_is_marked_for_business_flow(self) -> None:
        async def wait_result_handler() -> None:
            raise NonRecoverableStateError("Invalid number of inputs")

        fsm = WorkflowFSM(
            alpha_id="alpha-test",
            handlers={WorkflowState.WAIT_RESULT: wait_result_handler},
        )

        with self.assertRaises(WorkflowStateError) as caught:
            await fsm._run_state(WorkflowState.WAIT_RESULT)

        self.assertTrue(caught.exception.nonrecoverable)
        self.assertEqual(str(caught.exception), "Invalid number of inputs")


if __name__ == "__main__":
    unittest.main()
