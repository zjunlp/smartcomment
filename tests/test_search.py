"""Search and query-expansion tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_op,
    comment_op_scope,
    comment_session,
    comment_variable,
    enable_tracing,
)
from smartcomment.runtime.network import ExecNetwork
from smartcomment.runtime.graph import RuntimeGraph
from smartcomment.runtime.operation import RuntimeOp
from smartcomment.runtime.session import RuntimeSession
from tests.helpers import BaseTracingTest


class QueryExpansionTests(BaseTracingTest):
    """Test the expanded query API on ExecNetwork.

    Reuses a multi-session diamond graph identical to GraphQueryTests:

        Session "extract" (category="extraction"):
            alpha --[op1]--> beta
            alpha --[op1]--> gamma

        Session "search" (category="search"):
            beta  --[op2]--> delta
            gamma --[op2]--> delta

        Session "respond" (category="response"):
            delta --[op3]--> epsilon
    """

    graph: ExecNetwork
    op_ids: dict[str, str]

    @classmethod
    def setUpClass(cls) -> None:
        enable_tracing()
        import time

        _id = lambda v: str(v)
        cls.op_ids = {}

        with comment_graph(user_id="tester", project_id="test-proj") as g:
            with comment_session(
                session_id="ses-extract",
                session_name="extract",
                category="extraction",
            ):
                a = comment_variable(
                    "alpha", id_strategy=_id,
                    category="extraction", comment="root node",
                    to_runtime=True,
                )
                time.sleep(0.01)
                with comment_op_scope(
                    op_name="extract_op",
                    category="extraction",
                    comment="Extract B and C from A.",
                ) as op1:
                    cls.op_ids["extract"] = op1.op_id
                    comment_op(
                        inputs=[a],
                        outputs=[
                            ("beta", {"id_strategy": _id, "category": "extraction"}),
                            ("gamma", {"id_strategy": _id, "category": "extraction"}),
                        ],
                        op_name="extract",
                        category="extraction",
                        reuse_op=True,
                    )

            time.sleep(0.01)
            with comment_session(
                session_id="ses-search",
                session_name="search",
                category="search",
            ):
                b = g.get_latest_variable("beta")
                c = g.get_latest_variable("gamma")
                with comment_op_scope(
                    op_name="search_op",
                    category="search",
                    comment="Merge B and C into D.",
                ) as op2:
                    cls.op_ids["search"] = op2.op_id
                    comment_op(
                        inputs=[b, c],
                        outputs=[("delta", {"id_strategy": _id, "category": "search"})],
                        op_name="search",
                        category="search",
                        reuse_op=True,
                    )

            time.sleep(0.01)
            with comment_session(
                session_id="ses-respond",
                session_name="respond",
                category="response",
            ):
                d = g.get_latest_variable("delta")
                with comment_op_scope(
                    op_name="respond_op",
                    category="response",
                    comment="Produce E from D.",
                ) as op3:
                    cls.op_ids["respond"] = op3.op_id
                    comment_op(
                        inputs=[d],
                        outputs=[("epsilon", {"id_strategy": _id, "category": "response"})],
                        op_name="respond",
                        category="response",
                        reuse_op=True,
                    )

            cls.graph = g

    @classmethod
    def tearDownClass(cls) -> None:
        enable_tracing()

    # ------------------------------------------------------------------
    # Tier 1: get_variable
    # ------------------------------------------------------------------

    def test_get_variable_by_full_node_id(self) -> None:
        a = self.graph.get_latest_variable("alpha")
        result = self.graph.get_variable(a.full_node_id)
        self.assertEqual(result.full_node_id, a.full_node_id)
        self.assertEqual(result.name, "alpha")

    def test_get_variable_raises_on_missing(self) -> None:
        from smartcomment.runtime.errors import ExecNetworkKeyError

        with self.assertRaises(ExecNetworkKeyError):
            self.graph.get_variable("nonexistent@99")

    # ------------------------------------------------------------------
    # Tier 1: get_operation
    # ------------------------------------------------------------------

    def test_get_operation_by_id(self) -> None:
        op_id = self.op_ids["extract"]
        result = self.graph.get_operation(op_id)
        self.assertEqual(result.op_id, op_id)
        self.assertEqual(result.op_name, "extract_op")

    def test_get_operation_raises_on_missing(self) -> None:
        from smartcomment.runtime.errors import ExecNetworkKeyError

        with self.assertRaises(ExecNetworkKeyError):
            self.graph.get_operation("op-nonexistent")

    # ------------------------------------------------------------------
    # Tier 1: get_edge
    # ------------------------------------------------------------------

    def test_get_edge_by_id(self) -> None:
        edges = self.graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        first = edges[0]
        result = self.graph.get_edge(first.edge_id)
        self.assertEqual(result.edge_id, first.edge_id)

    def test_get_edge_raises_on_missing(self) -> None:
        from smartcomment.runtime.errors import ExecNetworkKeyError

        with self.assertRaises(ExecNetworkKeyError):
            self.graph.get_edge("edge-nonexistent")

    # ------------------------------------------------------------------
    # Tier 1: get_operations_by_variable
    # ------------------------------------------------------------------

    def test_get_operations_by_variable_middle_node(self) -> None:
        delta = self.graph.get_latest_variable("delta")
        result = self.graph.get_operations_by_variable(delta.full_node_id)
        self.assertTrue(all(isinstance(op, RuntimeOp) for op in result))

        op_ids = {op.op_id for op in result}
        self.assertIn(self.op_ids["search"], op_ids)
        self.assertIn(self.op_ids["respond"], op_ids)
        self.assertNotIn(self.op_ids["extract"], op_ids)

        timestamps = [op.created_at for op in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_get_operations_by_variable_root_node(self) -> None:
        alpha = self.graph.get_latest_variable("alpha")
        result = self.graph.get_operations_by_variable(alpha.full_node_id)
        self.assertEqual({op.op_id for op in result}, {self.op_ids["extract"]})

    def test_get_operations_by_variable_raises_on_missing(self) -> None:
        from smartcomment.runtime.errors import ExecNetworkKeyError

        with self.assertRaises(ExecNetworkKeyError):
            self.graph.get_operations_by_variable("nonexistent@99")

    # ------------------------------------------------------------------
    # Tier 2: search_sessions
    # ------------------------------------------------------------------

    def test_search_sessions_no_filters(self) -> None:
        result = self.graph.search_sessions()
        self.assertEqual(len(result), 3)
        self.assertTrue(all(isinstance(s, RuntimeSession) for s in result))
        timestamps = [s.created_at for s in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_search_sessions_by_name_regex(self) -> None:
        result = self.graph.search_sessions(name_pattern=r"^extract$")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].session_name, "extract")

    def test_search_sessions_by_name_regex_partial(self) -> None:
        result = self.graph.search_sessions(name_pattern=r"e")
        names = {s.session_name for s in result}
        self.assertIn("extract", names)
        self.assertIn("search", names)
        self.assertIn("respond", names)

    def test_search_sessions_by_name_regex_no_match(self) -> None:
        result = self.graph.search_sessions(name_pattern=r"^zzz$")
        self.assertEqual(len(result), 0)

    def test_search_sessions_by_single_category(self) -> None:
        result = self.graph.search_sessions(category="extraction")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].category, "extraction")

    def test_search_sessions_by_multiple_categories(self) -> None:
        result = self.graph.search_sessions(
            category=["extraction", "search"],
        )
        self.assertEqual(len(result), 2)
        cats = {s.category for s in result}
        self.assertEqual(cats, {"extraction", "search"})

    def test_search_sessions_by_time_range(self) -> None:
        all_sessions = self.graph.search_sessions()
        first = all_sessions[0]
        last = all_sessions[-1]
        result = self.graph.search_sessions(
            start_time=first.created_at,
            end_time=first.created_at,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].session_id, first.session_id)

    def test_search_sessions_combined_filters(self) -> None:
        result = self.graph.search_sessions(
            name_pattern="search",
            category="search",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].session_name, "search")

    # ------------------------------------------------------------------
    # Tier 2: search_operations
    # ------------------------------------------------------------------

    def test_search_operations_no_filters(self) -> None:
        result = self.graph.search_operations()
        self.assertGreaterEqual(len(result), 3)
        timestamps = [o.created_at for o in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_search_operations_by_name_regex(self) -> None:
        result = self.graph.search_operations(name_pattern=r"extract")
        names = {o.op_name for o in result}
        self.assertIn("extract_op", names)

    def test_search_operations_by_category(self) -> None:
        result = self.graph.search_operations(category="search")
        for op in result:
            self.assertEqual(op.category, "search")

    def test_search_operations_by_session_ids(self) -> None:
        result = self.graph.search_operations(session_ids="ses-extract")
        for op in result:
            self.assertEqual(op.session_id, "ses-extract")

    def test_search_operations_by_multiple_session_ids(self) -> None:
        result = self.graph.search_operations(
            session_ids=["ses-extract", "ses-respond"],
        )
        sids = {op.session_id for op in result}
        self.assertTrue(sids.issubset({"ses-extract", "ses-respond"}))

    def test_search_operations_combined_filters(self) -> None:
        result = self.graph.search_operations(
            name_pattern=r"respond",
            category="response",
            session_ids="ses-respond",
        )
        self.assertGreaterEqual(len(result), 1)
        for op in result:
            self.assertEqual(op.category, "response")
            self.assertEqual(op.session_id, "ses-respond")

    def test_search_operations_name_none_skipped(self) -> None:
        result = self.graph.search_operations(name_pattern=r"extract")
        for op in result:
            self.assertIsNotNone(op.op_name)

    # ------------------------------------------------------------------
    # Tier 2: search_variables
    # ------------------------------------------------------------------

    def test_search_variables_no_filters(self) -> None:
        result = self.graph.search_variables()
        self.assertEqual(len(result), 5)
        timestamps = [v.created_at for v in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_search_variables_by_name_regex(self) -> None:
        result = self.graph.search_variables(name_pattern=r"^al")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "alpha")

    def test_search_variables_by_name_regex_multiple_matches(self) -> None:
        result = self.graph.search_variables(name_pattern=r"a")
        names = {v.name for v in result}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertIn("gamma", names)
        self.assertIn("delta", names)

    def test_search_variables_by_category(self) -> None:
        result = self.graph.search_variables(category="extraction")
        self.assertEqual(len(result), 3)
        for v in result:
            self.assertEqual(v.category, "extraction")

    def test_search_variables_by_multiple_categories(self) -> None:
        result = self.graph.search_variables(
            category=["extraction", "response"],
        )
        cats = {v.category for v in result}
        self.assertTrue(cats.issubset({"extraction", "response"}))
        self.assertEqual(len(result), 4)

    def test_search_variables_by_session_ids(self) -> None:
        result = self.graph.search_variables(session_ids="ses-search")
        for v in result:
            self.assertEqual(v.session_id, "ses-search")

    def test_search_variables_by_class_name_none(self) -> None:
        result = self.graph.search_variables(class_name="NonExistent")
        self.assertEqual(len(result), 0)

    def test_search_variables_combined_filters(self) -> None:
        result = self.graph.search_variables(
            name_pattern=r"eta$",
            category="extraction",
        )
        names = {v.name for v in result}
        self.assertEqual(names, {"beta"})

    # ------------------------------------------------------------------
    # Tier 2: search_edges
    # ------------------------------------------------------------------

    def test_search_edges_no_filters(self) -> None:
        result = self.graph.search_edges()
        self.assertGreater(len(result), 0)
        timestamps = [e.created_at for e in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_search_edges_by_category(self) -> None:
        result = self.graph.search_edges(category="extraction")
        for e in result:
            self.assertEqual(e.category, "extraction")

    def test_search_edges_by_op_ids(self) -> None:
        op_id = self.op_ids["extract"]
        result = self.graph.search_edges(op_ids=op_id)
        for e in result:
            self.assertEqual(e.op_id, op_id)
        self.assertGreater(len(result), 0)

    def test_search_edges_by_session_ids(self) -> None:
        result = self.graph.search_edges(session_ids="ses-extract")
        for e in result:
            self.assertEqual(e.session_id, "ses-extract")

    def test_search_edges_by_multiple_op_ids(self) -> None:
        ids = [self.op_ids["extract"], self.op_ids["search"]]
        result = self.graph.search_edges(op_ids=ids)
        op_set = {e.op_id for e in result}
        self.assertTrue(op_set.issubset(set(ids)))

    def test_search_edges_combined_filters(self) -> None:
        result = self.graph.search_edges(
            category="response",
            session_ids="ses-respond",
        )
        for e in result:
            self.assertEqual(e.category, "response")
            self.assertEqual(e.session_id, "ses-respond")

    # ------------------------------------------------------------------
    # Tier 3: filter_by_operation
    # ------------------------------------------------------------------

    def test_filter_by_operation_single(self) -> None:
        op_id = self.op_ids["extract"]
        rg = self.graph.filter_by_operation(op_id)
        self.assertIsInstance(rg, RuntimeGraph)
        names = {n.name for n in rg.nodes}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertIn("gamma", names)
        self.assertNotIn("delta", names)
        self.assertNotIn("epsilon", names)
        for e in rg.edges:
            self.assertEqual(e.op_id, op_id)

    def test_filter_by_operation_multiple(self) -> None:
        ids = [self.op_ids["extract"], self.op_ids["respond"]]
        rg = self.graph.filter_by_operation(ids)
        names = {n.name for n in rg.nodes}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertIn("gamma", names)
        self.assertIn("delta", names)
        self.assertIn("epsilon", names)
        op_ids_in_graph = {o.op_id for o in rg.ops}
        self.assertTrue(op_ids_in_graph.issubset(set(ids)))

    def test_filter_by_operation_empty(self) -> None:
        rg = self.graph.filter_by_operation("op-nonexistent")
        self.assertTrue(rg.is_empty)
        self.assertEqual(rg.edge_count, 0)
        self.assertEqual(rg.op_count, 0)

    def test_filter_by_operation_preserves_ops(self) -> None:
        op_id = self.op_ids["search"]
        rg = self.graph.filter_by_operation(op_id)
        self.assertGreaterEqual(rg.op_count, 1)
        op_ids_in_result = {o.op_id for o in rg.ops}
        self.assertIn(op_id, op_ids_in_result)

    def test_filter_by_operation_includes_both_endpoints(self) -> None:
        op_id = self.op_ids["respond"]
        rg = self.graph.filter_by_operation(op_id)
        for e in rg.edges:
            self.assertIn(e.source_full_node_id, rg)
            self.assertIn(e.target_full_node_id, rg)

    # ------------------------------------------------------------------
    # Empty graph edge cases
    # ------------------------------------------------------------------

    def test_search_on_empty_graph(self) -> None:
        empty = ExecNetwork()
        self.assertEqual(len(empty.search_sessions()), 0)
        self.assertEqual(len(empty.search_operations()), 0)
        self.assertEqual(len(empty.search_variables()), 0)
        self.assertEqual(len(empty.search_edges()), 0)
        self.assertTrue(empty.filter_by_operation("x").is_empty)
