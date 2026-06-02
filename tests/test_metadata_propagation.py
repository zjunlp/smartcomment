"""Metadata propagation tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_op,
    comment_session,
    comment_variable,
    disable_tracing,
)
from tests.helpers import BaseTracingTest


class MetadataPropagationTests(BaseTracingTest):
    """Test that schema metadata stays on schema objects and
    propagate_attributes flows through TracingContext to Variables."""

    # ------------------------------------------------------------------
    # Schema metadata does NOT propagate
    # ------------------------------------------------------------------

    def test_graph_metadata_stays_on_graph(self) -> None:
        """comment_graph(metadata=...) writes only to the graph schema,
        not to TracingContext or downstream Variables."""
        with comment_graph(metadata={"graph_key": "gval"}) as graph:
            with comment_session(session_name="s1") as session:
                rv = comment_variable("hello", id_strategy="content", to_runtime=True)
                var = graph._driver.get_node(rv.full_node_id)

                self.assertEqual(graph.metadata.get("graph_key"), "gval")
                self.assertNotIn("graph_key", session.metadata)
                self.assertNotIn("graph_key", var.metadata)

    def test_session_metadata_stays_on_session(self) -> None:
        """comment_session(metadata=...) writes only to the session schema,
        not to TracingContext or downstream Variables."""
        with comment_graph() as graph:
            with comment_session(
                session_name="s1", metadata={"sess_key": "sval"}
            ) as session:
                rv = comment_variable("data", id_strategy="content", to_runtime=True)
                var = graph._driver.get_node(rv.full_node_id)

                self.assertIn("sess_key", session.metadata)
                self.assertNotIn("sess_key", var.metadata)

    # ------------------------------------------------------------------
    # propagate_attributes flows to Variables
    # ------------------------------------------------------------------

    def test_propagate_attributes_appears_on_variable(self) -> None:
        """propagate_attributes injects attributes into Variables."""
        from smartcomment import propagate_attributes

        with comment_graph() as graph:
            with propagate_attributes(run_id="exp-1"):
                with comment_session(session_name="s1"):
                    rv = comment_variable("hello", id_strategy="content", to_runtime=True)
                    var = graph._driver.get_node(rv.full_node_id)
                    self.assertEqual(var.metadata.get("run_id"), "exp-1")

    def test_propagate_attributes_not_on_graph_but_on_session(self) -> None:
        """propagate_attributes does NOT write to the graph (created
        before the scope), but DOES appear on sessions and ops
        created inside the scope."""
        from smartcomment import propagate_attributes

        with comment_graph() as graph:
            with propagate_attributes(run_id="exp-1"):
                with comment_session(session_name="s1") as session:
                    self.assertNotIn("run_id", graph.metadata)
                    self.assertIn("run_id", session.metadata)
                    self.assertEqual(session.metadata["run_id"], "exp-1")

    def test_propagate_attributes_nesting(self) -> None:
        """Nested propagate_attributes scopes merge and restore correctly."""
        from smartcomment import propagate_attributes

        with comment_graph() as graph:
            with propagate_attributes(level="outer", shared="a"):
                with comment_session(session_name="s1"):
                    with propagate_attributes(level="inner", extra="b"):
                        rv = comment_variable("inner_var", id_strategy="content", to_runtime=True)
                        var = graph._driver.get_node(rv.full_node_id)
                        self.assertEqual(var.metadata.get("level"), "inner")
                        self.assertEqual(var.metadata.get("shared"), "a")
                        self.assertEqual(var.metadata.get("extra"), "b")

                    rv2 = comment_variable("outer_var", id_strategy="content", to_runtime=True)
                    var2 = graph._driver.get_node(rv2.full_node_id)
                    self.assertEqual(var2.metadata.get("level"), "outer")
                    self.assertNotIn("extra", var2.metadata)

    def test_propagate_attributes_across_sessions(self) -> None:
        """Attributes set before comment_session flow into both sessions."""
        from smartcomment import propagate_attributes

        with comment_graph() as graph:
            with propagate_attributes(experiment="v1"):
                with comment_session(session_name="s1"):
                    rv1 = comment_variable("a", id_strategy="content", to_runtime=True)
                with comment_session(session_name="s2"):
                    rv2 = comment_variable("b", id_strategy="content", to_runtime=True)

                var1 = graph._driver.get_node(rv1.full_node_id)
                var2 = graph._driver.get_node(rv2.full_node_id)
                self.assertEqual(var1.metadata.get("experiment"), "v1")
                self.assertEqual(var2.metadata.get("experiment"), "v1")

    def test_propagate_attributes_appears_on_op(self) -> None:
        """propagate_attributes injects attributes into OpRecords."""
        from smartcomment import propagate_attributes

        with comment_graph() as graph:
            with propagate_attributes(run_id="exp-op"):
                with comment_session(session_name="s1"):
                    comment_op(
                        inputs=["a"],
                        outputs=["b"],
                        op_name="test_op",
                        id_strategy="content",
                    )

        ops = graph._driver.all_operations()
        self.assertTrue(len(ops) >= 1)
        self.assertEqual(ops[0].metadata.get("run_id"), "exp-op")

    # ------------------------------------------------------------------
    # propagate_attributes BEFORE comment_graph
    # ------------------------------------------------------------------

    def test_propagate_before_graph_injects_into_graph(self) -> None:
        """propagate_attributes before comment_graph injects attrs onto graph."""
        from smartcomment import propagate_attributes

        with propagate_attributes(run_id="pre-graph"):
            with comment_graph() as graph:
                self.assertEqual(graph.metadata.get("run_id"), "pre-graph")

    def test_propagate_before_graph_flows_to_session(self) -> None:
        """propagate_attributes before comment_graph flows into sessions."""
        from smartcomment import propagate_attributes

        with propagate_attributes(run_id="pre-graph"):
            with comment_graph() as graph:
                with comment_session(session_name="s1") as session:
                    self.assertEqual(session.metadata.get("run_id"), "pre-graph")

    def test_propagate_before_graph_flows_to_variable(self) -> None:
        """propagate_attributes before comment_graph flows into variables."""
        from smartcomment import propagate_attributes

        with propagate_attributes(run_id="pre-graph"):
            with comment_graph() as graph:
                with comment_session(session_name="s1"):
                    rv = comment_variable("hello", id_strategy="content", to_runtime=True)
                    var = graph._driver.get_node(rv.full_node_id)
                    self.assertEqual(var.metadata.get("run_id"), "pre-graph")

    def test_propagate_before_graph_flows_to_op(self) -> None:
        """propagate_attributes before comment_graph flows into operations."""
        from smartcomment import propagate_attributes

        with propagate_attributes(run_id="pre-graph"):
            with comment_graph() as graph:
                with comment_session(session_name="s1"):
                    comment_op(
                        inputs=["a"],
                        outputs=["b"],
                        op_name="test_op",
                        id_strategy="content",
                    )

        ops = graph._driver.all_operations()
        self.assertTrue(len(ops) >= 1)
        self.assertEqual(ops[0].metadata.get("run_id"), "pre-graph")

    def test_propagate_before_graph_merges_with_graph_metadata(self) -> None:
        """propagate_attributes and comment_graph(metadata=...) merge correctly."""
        from smartcomment import propagate_attributes

        with propagate_attributes(run_id="pre"):
            with comment_graph(metadata={"env": "test"}) as graph:
                self.assertEqual(graph.metadata.get("run_id"), "pre")
                self.assertEqual(graph.metadata.get("env"), "test")

    def test_propagate_attributes_noop_without_context(self) -> None:
        """propagate_attributes creates a root context but no graph, so
        entering and exiting is safe."""
        from smartcomment import propagate_attributes

        with propagate_attributes(run_id="orphan"):
            pass

    def test_propagate_attributes_noop_when_tracing_disabled(self) -> None:
        """propagate_attributes is a no-op when tracing is disabled."""
        from smartcomment import propagate_attributes

        disable_tracing()
        with propagate_attributes(run_id="off"):
            pass
