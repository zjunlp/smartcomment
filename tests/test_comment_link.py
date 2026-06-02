"""comment_link tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_session,
    comment_variable,
    disable_tracing,
)
from tests.helpers import BaseTracingTest


class CommentLinkTests(BaseTracingTest):
    """Tests for the comment_link function."""

    def test_comment_link_within_op_scope(self) -> None:
        """comment_link creates one edge inside an active comment_op_scope."""
        from smartcomment import comment_link, comment_op_scope

        with comment_graph() as graph:
            with comment_session(session_name="link-test"):
                a = comment_variable("alpha", id_strategy="content", to_runtime=True)
                b = comment_variable("beta", id_strategy="content", to_runtime=True)

                with comment_op_scope(op_name="linking") as op:
                    edge = comment_link(source=a, target=b)

        self.assertIsNotNone(edge)
        self.assertEqual(edge.source_full_node_id, a.full_node_id)
        self.assertEqual(edge.target_full_node_id, b.full_node_id)
        self.assertEqual(edge.op_id, op.op_id)
        self.assertEqual(graph.edge_count, 1)

    def test_comment_link_inherits_op_category_comment(self) -> None:
        """When category/comment are None, they default from the active op."""
        from smartcomment import comment_link, comment_op_scope

        with comment_graph() as graph:
            with comment_session():
                a = comment_variable("x", id_strategy="content", to_runtime=True)
                b = comment_variable("y", id_strategy="content", to_runtime=True)

                with comment_op_scope(
                    op_name="typed",
                    category="custom_cat",
                    comment="custom comment",
                ):
                    edge = comment_link(source=a, target=b)

        self.assertEqual(edge.category, "custom_cat")
        self.assertEqual(edge.comment, "custom comment")

    def test_comment_link_override_category_comment(self) -> None:
        """Explicit category/comment on comment_link override the op defaults."""
        from smartcomment import comment_link, comment_op_scope

        with comment_graph() as graph:
            with comment_session():
                a = comment_variable("x", id_strategy="content", to_runtime=True)
                b = comment_variable("y", id_strategy="content", to_runtime=True)

                with comment_op_scope(
                    op_name="parent",
                    category="parent_cat",
                    comment="parent_comment",
                ):
                    edge = comment_link(
                        source=a,
                        target=b,
                        category="child_cat",
                        comment="child_comment",
                    )

        self.assertEqual(edge.category, "child_cat")
        self.assertEqual(edge.comment, "child_comment")

    def test_comment_link_sentinel_op_without_scope(self) -> None:
        """Without an op scope, comment_link uses the sentinel operation."""
        from smartcomment import comment_link
        from smartcomment.runtime.network import none_op_id

        with comment_graph() as graph:
            with comment_session():
                a = comment_variable("p", id_strategy="content", to_runtime=True)
                b = comment_variable("q", id_strategy="content", to_runtime=True)
                edge = comment_link(source=a, target=b)

        self.assertEqual(edge.op_id, none_op_id())
        self.assertEqual(edge.category, "link")
        self.assertEqual(graph.edge_count, 1)

    def test_comment_link_multiple_edges_same_op(self) -> None:
        """Multiple comment_link calls within the same op scope create separate edges."""
        from smartcomment import comment_link, comment_op_scope

        with comment_graph() as graph:
            with comment_session():
                a = comment_variable("a", id_strategy="content", to_runtime=True)
                b = comment_variable("b", id_strategy="content", to_runtime=True)
                c = comment_variable("c", id_strategy="content", to_runtime=True)

                with comment_op_scope(op_name="fan-out"):
                    comment_link(source=a, target=b, category="primary")
                    comment_link(source=a, target=c, category="secondary")

        self.assertEqual(graph.edge_count, 2)
        edges = graph.get_all_edges()
        categories = {e.category for e in edges}
        self.assertEqual(categories, {"primary", "secondary"})

    def test_comment_link_auto_creates_variables(self) -> None:
        """Raw values passed to comment_link are auto-created as variables."""
        from smartcomment import comment_link

        with comment_graph() as graph:
            with comment_session():
                edge = comment_link(
                    source=("src_val", {"id_strategy": "content"}),
                    target=("tgt_val", {"id_strategy": "content"}),
                )

        self.assertIsNotNone(edge)
        self.assertEqual(graph.node_count, 2)
        self.assertEqual(graph.edge_count, 1)

    def test_comment_link_noop_when_disabled(self) -> None:
        """comment_link returns None when tracing is disabled."""
        from smartcomment import comment_link

        disable_tracing()
        result = comment_link(source="a", target="b")
        self.assertIsNone(result)

    def test_comment_link_edge_metadata(self) -> None:
        """edge_metadata is attached to the created edge."""
        from smartcomment import comment_link

        with comment_graph() as graph:
            with comment_session():
                a = comment_variable("m", id_strategy="content", to_runtime=True)
                b = comment_variable("n", id_strategy="content", to_runtime=True)
                edge = comment_link(
                    source=a,
                    target=b,
                    edge_metadata={"importance": "high"},
                )

        self.assertEqual(edge.metadata["importance"], "high")
