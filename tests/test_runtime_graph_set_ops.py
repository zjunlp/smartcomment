"""RuntimeGraph set-operation tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_op,
    comment_session,
    comment_variable,
    enable_tracing,
)
from smartcomment.runtime.graph import RuntimeGraph
from tests.helpers import BaseTracingTest


class RuntimeGraphSetOperationTests(BaseTracingTest):
    """Test set operations (intersection, union, difference, symmetric
    difference) and comparison operators on RuntimeGraph.

    Builds two overlapping RuntimeGraphs from the same ExecNetwork:

        graph_a  (filter_by_category "extraction"):  alpha, beta, gamma  +  op1
        graph_b  (filter_by_category {"extraction", "search"}):  alpha, beta, gamma, delta  +  op1, op2

    Overlap on {alpha, beta, gamma} and op1.
    """

    graph_a: RuntimeGraph
    graph_b: RuntimeGraph
    full_graph: RuntimeGraph

    @classmethod
    def setUpClass(cls) -> None:
        enable_tracing()
        import time

        _id = lambda v: str(v)

        with comment_graph() as g:
            with comment_session(session_name="s1"):
                a = comment_variable("alpha", id_strategy=_id,
                                     category="extraction", to_runtime=True)
                time.sleep(0.01)
                comment_op(
                    inputs=[a],
                    outputs=[
                        ("beta", {"id_strategy": _id, "category": "extraction"}),
                        ("gamma", {"id_strategy": _id, "category": "extraction"}),
                    ],
                    op_name="op1", category="extraction",
                )

            time.sleep(0.01)
            with comment_session(session_name="s2"):
                b = g.get_latest_variable("beta")
                c = g.get_latest_variable("gamma")
                comment_op(
                    inputs=[b, c],
                    outputs=[("delta", {"id_strategy": _id, "category": "search"})],
                    op_name="op2", category="search",
                )

            time.sleep(0.01)
            with comment_session(session_name="s3"):
                d = g.get_latest_variable("delta")
                comment_op(
                    inputs=[d],
                    outputs=[("epsilon", {"id_strategy": _id, "category": "response"})],
                    op_name="op3", category="response",
                )

            cls.full_graph = g.to_runtime_graph()
            cls.graph_a = cls.full_graph.filter_by_category("extraction")
            cls.graph_b = cls.full_graph.filter_by_category({"extraction", "search"})

    @classmethod
    def tearDownClass(cls) -> None:
        enable_tracing()

    # ------------------------------------------------------------------
    # Intersection (__and__)
    # ------------------------------------------------------------------

    def test_intersection_nodes(self) -> None:
        result = self.graph_a & self.graph_b
        names = {n.name for n in result.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma"})

    def test_intersection_ops(self) -> None:
        result = self.graph_a & self.graph_b
        op_names = {o.op_name for o in result.ops}
        self.assertEqual(op_names, {"op1"})

    def test_intersection_edges_filtered_by_ops_then_nodes(self) -> None:
        result = self.graph_a & self.graph_b
        for e in result.edges:
            self.assertIn(e.op_id, result._op_ids)
            self.assertIn(e.source_full_node_id, result._node_ids)
            self.assertIn(e.target_full_node_id, result._node_ids)

    def test_intersection_commutative(self) -> None:
        self.assertEqual(self.graph_a & self.graph_b,
                         self.graph_b & self.graph_a)

    def test_intersection_with_self(self) -> None:
        self.assertEqual(self.graph_a & self.graph_a, self.graph_a)

    def test_intersection_with_empty(self) -> None:
        empty = RuntimeGraph(nodes=[], edges=[], ops=[])
        result = self.graph_a & empty
        self.assertEqual(len(result), 0)
        self.assertEqual(result.op_count, 0)
        self.assertEqual(result.edge_count, 0)

    # ------------------------------------------------------------------
    # Union (__or__)
    # ------------------------------------------------------------------

    def test_union_nodes(self) -> None:
        result = self.graph_a | self.graph_b
        names = {n.name for n in result.nodes}
        expected_a = {n.name for n in self.graph_a.nodes}
        expected_b = {n.name for n in self.graph_b.nodes}
        self.assertEqual(names, expected_a | expected_b)

    def test_union_ops(self) -> None:
        result = self.graph_a | self.graph_b
        op_ids = {o.op_id for o in result.ops}
        a_ids = {o.op_id for o in self.graph_a.ops}
        b_ids = {o.op_id for o in self.graph_b.ops}
        self.assertEqual(op_ids, a_ids | b_ids)

    def test_union_edges(self) -> None:
        result = self.graph_a | self.graph_b
        edge_ids = {e.edge_id for e in result.edges}
        a_ids = {e.edge_id for e in self.graph_a.edges}
        b_ids = {e.edge_id for e in self.graph_b.edges}
        self.assertEqual(edge_ids, a_ids | b_ids)

    def test_union_commutative(self) -> None:
        self.assertEqual(self.graph_a | self.graph_b,
                         self.graph_b | self.graph_a)

    def test_union_with_self(self) -> None:
        self.assertEqual(self.graph_a | self.graph_a, self.graph_a)

    def test_union_with_empty(self) -> None:
        empty = RuntimeGraph(nodes=[], edges=[], ops=[])
        self.assertEqual(self.graph_a | empty, self.graph_a)

    # ------------------------------------------------------------------
    # Difference (__sub__)
    # ------------------------------------------------------------------

    def test_difference_nodes(self) -> None:
        result = self.graph_b - self.graph_a
        names = {n.name for n in result.nodes}
        self.assertEqual(names, {"delta"})

    def test_difference_ops_derived_from_edges(self) -> None:
        """Ops are derived from surviving edges.  op2's edges connect
        shared nodes (beta, gamma) to the unique node (delta), so no
        edge survives the node filter and op2 is absent."""
        result = self.graph_b - self.graph_a
        self.assertEqual(result.op_count, 0)

    def test_difference_edges_respect_ops_and_nodes(self) -> None:
        result = self.graph_b - self.graph_a
        for e in result.edges:
            self.assertIn(e.op_id, result._op_ids)
            self.assertIn(e.source_full_node_id, result._node_ids)
            self.assertIn(e.target_full_node_id, result._node_ids)

    def test_difference_self_is_empty(self) -> None:
        result = self.graph_a - self.graph_a
        self.assertTrue(result.is_empty)
        self.assertEqual(result.op_count, 0)
        self.assertEqual(result.edge_count, 0)

    def test_difference_a_minus_b(self) -> None:
        result = self.graph_a - self.graph_b
        self.assertTrue(result.is_empty)

    # ------------------------------------------------------------------
    # Symmetric difference (__xor__)
    # ------------------------------------------------------------------

    def test_symmetric_difference_nodes(self) -> None:
        result = self.graph_a ^ self.graph_b
        names = {n.name for n in result.nodes}
        self.assertEqual(names, {"delta"})

    def test_symmetric_difference_ops_derived_from_edges(self) -> None:
        """Same reasoning as difference: op2's edges touch shared nodes,
        so no edge survives and op2 is absent."""
        result = self.graph_a ^ self.graph_b
        self.assertEqual(result.op_count, 0)

    def test_symmetric_difference_commutative(self) -> None:
        self.assertEqual(self.graph_a ^ self.graph_b,
                         self.graph_b ^ self.graph_a)

    def test_symmetric_difference_self_is_empty(self) -> None:
        result = self.graph_a ^ self.graph_a
        self.assertTrue(result.is_empty)

    # ------------------------------------------------------------------
    # Equality (__eq__)
    # ------------------------------------------------------------------

    def test_equality_same_graph(self) -> None:
        self.assertEqual(self.graph_a, self.graph_a)

    def test_equality_reconstructed(self) -> None:
        copy = RuntimeGraph(
            nodes=list(self.graph_a.nodes),
            edges=list(self.graph_a.edges),
            ops=list(self.graph_a.ops),
        )
        self.assertEqual(self.graph_a, copy)

    def test_inequality_different_nodes(self) -> None:
        self.assertNotEqual(self.graph_a, self.graph_b)

    def test_equality_not_implemented_for_other_types(self) -> None:
        self.assertNotEqual(self.graph_a, "not a graph")

    # ------------------------------------------------------------------
    # Subset / superset
    # ------------------------------------------------------------------

    def test_issubset(self) -> None:
        self.assertTrue(self.graph_a.issubset(self.graph_b))

    def test_issubset_self(self) -> None:
        self.assertTrue(self.graph_a.issubset(self.graph_a))

    def test_not_issubset(self) -> None:
        self.assertFalse(self.graph_b.issubset(self.graph_a))

    def test_issuperset(self) -> None:
        self.assertTrue(self.graph_b.issuperset(self.graph_a))

    def test_le_operator(self) -> None:
        self.assertTrue(self.graph_a <= self.graph_b)

    def test_ge_operator(self) -> None:
        self.assertTrue(self.graph_b >= self.graph_a)

    def test_lt_operator(self) -> None:
        self.assertTrue(self.graph_a < self.graph_b)

    def test_lt_not_equal(self) -> None:
        self.assertFalse(self.graph_a < self.graph_a)

    def test_gt_operator(self) -> None:
        self.assertTrue(self.graph_b > self.graph_a)

    def test_gt_not_equal(self) -> None:
        self.assertFalse(self.graph_a > self.graph_a)

    # ------------------------------------------------------------------
    # Set-algebraic identities
    # ------------------------------------------------------------------

    def test_union_minus_intersection_equals_xor(self) -> None:
        union = self.graph_a | self.graph_b
        inter = self.graph_a & self.graph_b
        xor = self.graph_a ^ self.graph_b
        self.assertEqual(union - inter, xor)

    def test_union_of_diff_and_intersection_covers_nodes(self) -> None:
        """Node-level identity: (A & B) | (B - A) covers B's nodes.
        Op-level identity does not hold in general because ops are
        derived from surviving edges, not independently set-operated."""
        diff = self.graph_b - self.graph_a
        inter = self.graph_a & self.graph_b
        self.assertEqual((inter | diff)._node_ids, self.graph_b._node_ids)

    def test_full_graph_superset_of_all(self) -> None:
        self.assertTrue(self.graph_a <= self.full_graph)
        self.assertTrue(self.graph_b <= self.full_graph)

    # ------------------------------------------------------------------
    # Edge semantics: intersection filters edges via ops first
    # ------------------------------------------------------------------

    def test_intersection_no_cross_op_edge_leak(self) -> None:
        """Edges belonging to ops outside the intersection must not appear."""
        result = self.graph_a & self.graph_b
        result_op_ids = {o.op_id for o in result.ops}
        for e in result.edges:
            self.assertIn(e.op_id, result_op_ids,
                          "Edge op_id must be in the intersected ops")

    def test_difference_no_dangling_edges(self) -> None:
        """After difference, no edge should reference a removed node."""
        result = self.graph_b - self.graph_a
        node_ids = {n.full_node_id for n in result.nodes}
        for e in result.edges:
            self.assertIn(e.source_full_node_id, node_ids)
            self.assertIn(e.target_full_node_id, node_ids)
