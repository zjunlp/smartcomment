"""Context-manager guard tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_mutation,
    comment_op,
    comment_session,
    comment_variable,
    disable_tracing,
)
from tests.helpers import BaseTracingTest


class StrictContextTests(BaseTracingTest):
    """Verify that APIs raise RuntimeError when required context is missing,
    and that comment_op_scope auto-creates an anonymous session."""

    # ------------------------------------------------------------------
    # comment_session raises without graph
    # ------------------------------------------------------------------

    def test_comment_session_raises_without_graph(self) -> None:
        """RuntimeError matches context.py: backtick-quoted ``comment_session``."""
        with self.assertRaises(RuntimeError) as ctx:
            with comment_session(session_name="orphan"):
                pass
        msg = str(ctx.exception)
        self.assertIn("`comment_session`", msg)
        self.assertIn("active graph context", msg)

    def test_comment_session_noop_when_tracing_disabled(self) -> None:
        """comment_session yields None when tracing is disabled, even without graph."""
        disable_tracing()
        with comment_session(session_name="off") as s:
            self.assertIsNone(s)

    # ------------------------------------------------------------------
    # comment_op_scope raises without graph, auto-creates session
    # ------------------------------------------------------------------

    def test_comment_op_scope_raises_without_graph(self) -> None:
        """RuntimeError matches context.py: backtick-quoted ``comment_op_scope``."""
        from smartcomment import comment_op_scope

        with self.assertRaises(RuntimeError) as ctx:
            with comment_op_scope(op_name="orphan"):
                pass
        msg = str(ctx.exception)
        self.assertIn("`comment_op_scope`", msg)
        self.assertIn("active graph context", msg)

    def test_comment_op_scope_auto_creates_session(self) -> None:
        """comment_op_scope auto-creates an anonymous session when none exists."""
        from smartcomment import comment_op_scope

        with comment_graph() as graph:
            with comment_op_scope(op_name="auto") as op:
                self.assertIsNotNone(op)
                rv = comment_variable("hello", id_strategy="content", to_runtime=True)
                var = graph._driver.get_node(rv.full_node_id)
                self.assertNotEqual(var.session_id, "__unknown__")

    def test_comment_op_scope_auto_session_cleaned_up(self) -> None:
        """The auto-created session is removed from context after scope exits."""
        from smartcomment import comment_op_scope
        from smartcomment.runtime.context import _SESSION

        with comment_graph():
            with comment_op_scope(op_name="auto"):
                self.assertIsNotNone(_SESSION.get())
            self.assertIsNone(_SESSION.get())

    def test_comment_op_scope_uses_existing_session(self) -> None:
        """When a session already exists, comment_op_scope uses it."""
        from smartcomment import comment_op_scope

        with comment_graph() as graph:
            with comment_session(session_name="explicit") as session:
                with comment_op_scope(op_name="inner") as op:
                    rv = comment_variable("val", id_strategy="content", to_runtime=True)
                    var = graph._driver.get_node(rv.full_node_id)
                    self.assertEqual(var.session_id, session.session_id)

    def test_comment_op_scope_auto_session_gets_propagated_attrs(self) -> None:
        """Auto-created session inherits propagated attributes."""
        from smartcomment import comment_op_scope, propagate_attributes

        with comment_graph() as graph:
            with propagate_attributes(run_id="auto-test"):
                with comment_op_scope(op_name="auto") as op:
                    self.assertIsNotNone(op)

    # ------------------------------------------------------------------
    # comment_variable raises without graph
    # ------------------------------------------------------------------

    def test_comment_variable_raises_without_graph(self) -> None:
        """comment_variable raises RuntimeError when no graph is active."""
        with self.assertRaises(RuntimeError) as ctx:
            comment_variable("orphan", id_strategy="content")
        self.assertIn("comment_variable", str(ctx.exception))

    def test_comment_variable_noop_when_tracing_disabled(self) -> None:
        """comment_variable returns the raw value when tracing is disabled."""
        disable_tracing()
        result = comment_variable("hello", id_strategy="content")
        self.assertEqual(result, "hello")

    # ------------------------------------------------------------------
    # comment_op raises without graph
    # ------------------------------------------------------------------

    def test_comment_op_raises_without_graph(self) -> None:
        """comment_op raises RuntimeError when no graph is active."""
        with self.assertRaises(RuntimeError) as ctx:
            comment_op(
                inputs=["a"],
                outputs=["b"],
                op_name="orphan",
                id_strategy="content",
            )
        self.assertIn("comment_op", str(ctx.exception))

    def test_comment_op_noop_when_tracing_disabled(self) -> None:
        """comment_op returns None when tracing is disabled."""
        disable_tracing()
        result = comment_op(
            inputs=["a"], outputs=["b"], op_name="off", id_strategy="content"
        )
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # comment_mutation raises without graph
    # ------------------------------------------------------------------

    def test_comment_mutation_raises_without_graph(self) -> None:
        """comment_mutation raises RuntimeError when no graph is active."""
        with self.assertRaises(RuntimeError) as ctx:
            with comment_mutation(target="old", id_strategy="content"):
                pass
        self.assertIn("comment_mutation", str(ctx.exception))

    def test_comment_mutation_noop_when_tracing_disabled(self) -> None:
        """comment_mutation result is None when tracing is disabled."""
        disable_tracing()
        with comment_mutation(target="old", id_strategy="content") as scope:
            pass
        self.assertIsNone(scope.result)
