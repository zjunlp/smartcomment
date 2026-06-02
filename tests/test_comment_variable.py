"""comment_variable runtime handle tests."""

from __future__ import annotations

from smartcomment import (
    IdentityRegistry,
    comment_graph,
    comment_session,
    comment_variable,
    current_context,
)
from smartcomment.runtime.variable import RuntimeVariable
from tests.helpers import BaseTracingTest


class CommentVariableRuntimeHandleTests(BaseTracingTest):
    """Test ``comment_variable`` behavior when fed an existing RuntimeVariable.

    Feeding a runtime handle back through ``comment_variable`` is a common
    accidental pattern once users stash ``to_runtime=True`` results in long-
    lived collections. The function must short-circuit so that no spurious
    nodes are written and no identity resolution is attempted on the handle
    object itself.
    """

    def test_passing_runtime_variable_is_idempotent(self) -> None:
        """A RuntimeVariable input returns the same handle without new nodes."""
        with comment_graph() as graph:
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                node_count_before = len(graph.get_all_nodes())

                returned = comment_variable(rv)

                node_count_after = len(graph.get_all_nodes())

        self.assertIs(returned, rv)
        self.assertEqual(node_count_before, node_count_after)

    def test_passing_runtime_variable_with_to_runtime_flag(self) -> None:
        """``to_runtime=True`` is a no-op when the input is already a handle."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                returned = comment_variable(rv, to_runtime=True)

        self.assertIs(returned, rv)

    def test_passing_runtime_variable_registers_variable_name(self) -> None:
        """``variable_name`` still registers the rv under the tracing context."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                returned = comment_variable(rv, variable_name="greeting")

                ctx = current_context()
                self.assertIsNotNone(ctx)
                looked_up = ctx.get_variable("greeting")

        self.assertIs(returned, rv)
        self.assertIs(looked_up, rv)

    def test_does_not_attempt_identity_resolution_on_handle(self) -> None:
        """No IdentityRegistry lookup happens for ``RuntimeVariable`` inputs.

        Without the short-circuit, ``_resolve_identity`` would call
        ``IdentityRegistry.resolve(rv)`` which requires a registered
        ``RuntimeVariable`` strategy. We assert that no such strategy is
        registered yet the call still succeeds, which can only be the case
        if the short-circuit bypasses identity resolution entirely.
        """
        with self.assertRaises(KeyError):
            IdentityRegistry.get(RuntimeVariable)
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                returned = comment_variable(rv)

        self.assertIs(returned, rv)

    def test_rv_short_circuit_is_silent_at_warning_level(self) -> None:
        """The RV short-circuit does not emit any WARNING-level log record.

        Extra options supplied alongside an already-materialized runtime
        handle have no effect on the graph node, but the short-circuit
        stays quiet at WARNING level so it can be used freely in hot
        paths. It may still emit a DEBUG record (registering under
        ``variable_name``), which is fine and not asserted here.
        """
        from smartcomment.logging import logger

        records: list[str] = []
        handler_id = logger.add(
            lambda msg: records.append(msg.record["message"]),
            level="WARNING",
        )
        try:
            with comment_graph():
                with comment_session(session_name="s"):
                    rv = comment_variable(
                        "hello",
                        id_strategy="content",
                        to_runtime=True,
                    )
                    comment_variable(rv, comment="ignored", metadata={"k": "v"})
                    comment_variable(rv, variable_name="x_alias")
        finally:
            logger.remove(handler_id)

        self.assertEqual(
            records,
            [],
            msg=f"Unexpected WARNING-level records: {records!r}",
        )
