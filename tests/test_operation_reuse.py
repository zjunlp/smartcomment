"""Operation reuse (reuse_op) tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_mutation,
    comment_op,
    comment_op_scope,
)
from tests.helpers import BaseTracingTest


class ReuseOpTests(BaseTracingTest):
    """Tests for the reuse_op parameter on comment_op and comment_mutation."""

    # ------------------------------------------------------------------
    # comment_op reuse_op
    # ------------------------------------------------------------------

    def test_comment_op_reuse_op_false_creates_new_op(self) -> None:
        """Default reuse_op=False always creates a new operation."""
        with comment_graph() as graph:
            with comment_op_scope(op_name="outer") as outer_op:
                comment_op(
                    inputs=["a"], outputs=["b"],
                    op_name="inner", id_strategy="content",
                )

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 2)
        op_names = {op.op_name for op in ops}
        self.assertIn("outer", op_names)
        self.assertIn("inner", op_names)

    def test_comment_op_reuse_op_true_reuses_outer(self) -> None:
        """reuse_op=True attributes edges to the active operation scope."""
        with comment_graph() as graph:
            with comment_op_scope(op_name="outer") as outer_op:
                comment_op(
                    inputs=["a"], outputs=["b"],
                    op_name="inner", id_strategy="content",
                    reuse_op=True,
                )

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "outer")

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertEqual(edge.op_id, outer_op.op_id)

    def test_comment_op_reuse_op_true_no_scope_creates_new(self) -> None:
        """reuse_op=True falls back to creating a new op when no scope is active."""
        with comment_graph() as graph:
            comment_op(
                inputs=["a"], outputs=["b"],
                op_name="standalone", id_strategy="content",
                reuse_op=True,
            )

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "standalone")

    def test_comment_op_reuse_op_category_on_edges(self) -> None:
        """Category from comment_op is applied to edges when reusing."""
        with comment_graph() as graph:
            with comment_op_scope(op_name="outer", category="outer_cat"):
                comment_op(
                    inputs=["x"], outputs=["y"],
                    op_name="inner", id_strategy="content",
                    category="inner_cat", comment="inner edge",
                    reuse_op=True,
                )

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertEqual(edge.category, "inner_cat")
            self.assertEqual(edge.comment, "inner edge")

    # ------------------------------------------------------------------
    # comment_op with op_name=None
    # ------------------------------------------------------------------

    def test_comment_op_no_name_reuses_outer(self) -> None:
        """op_name=None reuses the active operation scope."""
        with comment_graph() as graph:
            with comment_op_scope(op_name="outer") as outer_op:
                comment_op(
                    inputs=["a"], outputs=["b"],
                    id_strategy="content",
                )

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "outer")

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertEqual(edge.op_id, outer_op.op_id)

    def test_comment_op_no_name_no_scope_raises(self) -> None:
        """op_name=None without an active scope raises RuntimeError."""
        with comment_graph() as graph:
            with self.assertRaises(RuntimeError):
                comment_op(
                    inputs=["a"], outputs=["b"],
                    id_strategy="content",
                )

    # ------------------------------------------------------------------
    # comment_mutation reuse_op
    # ------------------------------------------------------------------

    def test_mutation_reuse_op_false_creates_new_op(self) -> None:
        """Default reuse_op=False creates a separate mutation operation."""
        data = {"id": "m1", "text": "original"}

        with comment_graph() as graph:
            with comment_op_scope(op_name="outer") as outer_op:
                with comment_mutation(
                    target=data,
                    id_strategy=lambda d: d["id"],
                    mutation_name="update_text",
                ):
                    data["text"] = "modified"

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 2)
        op_names = {op.op_name for op in ops}
        self.assertIn("outer", op_names)
        self.assertIn("update_text", op_names)

    def test_mutation_reuse_op_true_reuses_outer(self) -> None:
        """reuse_op=True attributes mutation edges to the active op scope."""
        data = {"id": "m2", "text": "before"}

        with comment_graph() as graph:
            with comment_op_scope(op_name="pipeline") as outer_op:
                with comment_mutation(
                    target=data,
                    id_strategy=lambda d: d["id"],
                    mutation_name="ignored",
                    mutation_comment="updating text",
                    reuse_op=True,
                ) as scope:
                    data["text"] = "after"

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "pipeline")

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertEqual(edge.op_id, outer_op.op_id)

        self.assertIsNotNone(scope.result)
        self.assertEqual(scope.result.version, 2)

    def test_mutation_reuse_op_true_no_scope_creates_new(self) -> None:
        """reuse_op=True falls back to creating a mutation op when no scope."""
        data = {"id": "m3", "text": "old"}

        with comment_graph() as graph:
            with comment_mutation(
                target=data,
                id_strategy=lambda d: d["id"],
                mutation_name="fallback_mut",
                reuse_op=True,
            ) as scope:
                data["text"] = "new"

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "fallback_mut")

    def test_mutation_reuse_op_version_bump_always_happens(self) -> None:
        """Version bump occurs regardless of reuse_op setting."""
        data = {"id": "m4", "val": 1}

        with comment_graph() as graph:
            with comment_op_scope(op_name="outer"):
                with comment_mutation(
                    target=data,
                    id_strategy=lambda d: d["id"],
                    reuse_op=True,
                ) as scope:
                    data["val"] = 2

        self.assertIsNotNone(scope.result)
        self.assertEqual(scope.result.version, 2)

        nodes = graph.get_all_nodes()
        versions = sorted(n.version for n in nodes if n.name == "m4")
        self.assertEqual(versions, [1, 2])

    def test_mutation_reuse_op_category_on_edges(self) -> None:
        """mutation_category is applied to edges when reusing outer op."""
        data = {"id": "m5", "x": 0}

        with comment_graph() as graph:
            with comment_op_scope(op_name="outer", category="outer_cat"):
                with comment_mutation(
                    target=data,
                    id_strategy=lambda d: d["id"],
                    mutation_category="mut_cat",
                    mutation_comment="mutated",
                    reuse_op=True,
                ):
                    data["x"] = 1

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertEqual(edge.category, "mut_cat")
