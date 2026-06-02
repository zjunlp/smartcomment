"""Execution graph query and serialization tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_op,
    comment_session,
    comment_variable,
    enable_tracing,
)
from smartcomment.runtime.network import ExecNetwork
from smartcomment.runtime.graph import RuntimeGraph
from tests.helpers import BaseTracingTest


class GraphQueryTests(BaseTracingTest):
    """Test ExecNetwork graph query interfaces with a multi-session diamond graph.

    The fixture builds the following topology across three sessions using
    a literal identity strategy (lambda v: v) so that variable names
    equal the string values:

        Session "extract" (category="extraction"):
            alpha --[op1]--> beta
            alpha --[op1]--> gamma

        Session "search" (category="search"):
            beta  --[op2]--> delta
            gamma --[op2]--> delta

        Session "respond" (category="response"):
            delta --[op3]--> epsilon

    Root: alpha   Leaf: epsilon   Diamond: alpha -> {beta, gamma} -> delta -> epsilon
    """

    graph: ExecNetwork

    @classmethod
    def setUpClass(cls) -> None:
        enable_tracing()
        import time

        _id = lambda v: str(v)

        with comment_graph(user_id="tester", project_id="test-proj") as g:
            with comment_session(session_name="extract"):
                a = comment_variable("alpha", id_strategy=_id,
                                     category="extraction", comment="root node",
                                     to_runtime=True)
                time.sleep(0.01)
                comment_op(
                    inputs=[a],
                    outputs=[
                        ("beta", {"id_strategy": _id, "category": "extraction"}),
                        ("gamma", {"id_strategy": _id, "category": "extraction"}),
                    ],
                    op_name="extract",
                    category="extraction",
                    comment="Extract B and C from A.",
                )

            time.sleep(0.01)
            with comment_session(session_name="search"):
                b = g.get_latest_variable("beta")
                c = g.get_latest_variable("gamma")
                comment_op(
                    inputs=[b, c],
                    outputs=[("delta", {"id_strategy": _id, "category": "search"})],
                    op_name="search",
                    category="search",
                    comment="Merge B and C into D.",
                )

            time.sleep(0.01)
            with comment_session(session_name="respond"):
                d = g.get_latest_variable("delta")
                comment_op(
                    inputs=[d],
                    outputs=[("epsilon", {"id_strategy": _id, "category": "response"})],
                    op_name="respond",
                    category="response",
                    comment="Produce E from D.",
                )

            cls.graph = g

    @classmethod
    def tearDownClass(cls) -> None:
        enable_tracing()

    # ------------------------------------------------------------------
    # Size and utility
    # ------------------------------------------------------------------

    def test_len(self) -> None:
        """__len__ returns the node count."""
        self.assertEqual(len(self.graph), 5)

    def test_node_count(self) -> None:
        self.assertEqual(self.graph.node_count, 5)

    def test_edge_count(self) -> None:
        self.assertTrue(self.graph.edge_count >= 5)

    def test_op_count(self) -> None:
        self.assertEqual(self.graph.op_count, 3)

    def test_is_empty_false(self) -> None:
        self.assertFalse(self.graph.is_empty)

    def test_is_empty_true(self) -> None:
        empty = ExecNetwork()
        self.assertTrue(empty.is_empty)

    # ------------------------------------------------------------------
    # Bulk accessors
    # ------------------------------------------------------------------

    def test_get_all_nodes(self) -> None:
        nodes = self.graph.get_all_nodes()
        self.assertEqual(len(nodes), 5)
        names = {n.name for n in nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "delta", "epsilon"})

    def test_get_all_edges(self) -> None:
        edges = self.graph.get_all_edges()
        self.assertTrue(len(edges) >= 5)

    def test_get_all_operations(self) -> None:
        ops = self.graph.get_all_operations()
        self.assertEqual(len(ops), 3)
        op_names = {o.op_name for o in ops}
        self.assertEqual(op_names, {"extract", "search", "respond"})

    # ------------------------------------------------------------------
    # to_runtime_graph
    # ------------------------------------------------------------------

    def test_to_runtime_graph(self) -> None:
        rg = self.graph.to_runtime_graph()
        self.assertEqual(len(rg), 5)
        self.assertEqual(rg.edge_count, self.graph.edge_count)
        self.assertEqual(rg.op_count, 3)
        self.assertFalse(rg.is_empty)

    # ------------------------------------------------------------------
    # Leaf and root nodes
    # ------------------------------------------------------------------

    def test_get_root_nodes(self) -> None:
        roots = self.graph.get_root_nodes()
        root_names = {r.name for r in roots}
        self.assertIn("alpha", root_names)
        self.assertNotIn("epsilon", root_names)

    def test_get_leaf_nodes(self) -> None:
        leaves = self.graph.get_leaf_nodes()
        leaf_names = {l.name for l in leaves}
        self.assertIn("epsilon", leaf_names)
        self.assertNotIn("alpha", leaf_names)

    # ------------------------------------------------------------------
    # filter_by_category
    # ------------------------------------------------------------------

    def test_filter_by_single_category(self) -> None:
        rg = self.graph.filter_by_category("extraction")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma"})

    def test_filter_by_multiple_categories(self) -> None:
        rg = self.graph.filter_by_category(["extraction", "search"])
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "delta"})

    def test_filter_by_category_empty(self) -> None:
        rg = self.graph.filter_by_category("nonexistent")
        self.assertTrue(rg.is_empty)

    # ------------------------------------------------------------------
    # BFS forward
    # ------------------------------------------------------------------

    def test_bfs_forward_from_root(self) -> None:
        a = self.graph.get_latest_variable("alpha")
        rg = self.graph.bfs(a.full_node_id, "forward")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "delta", "epsilon"})

    def test_bfs_forward_from_middle(self) -> None:
        d = self.graph.get_latest_variable("delta")
        rg = self.graph.bfs(d.full_node_id, "forward")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"delta", "epsilon"})

    # ------------------------------------------------------------------
    # BFS backward
    # ------------------------------------------------------------------

    def test_bfs_backward_from_leaf(self) -> None:
        e = self.graph.get_latest_variable("epsilon")
        rg = self.graph.bfs(e.full_node_id, "backward")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "delta", "epsilon"})

    def test_bfs_backward_from_middle(self) -> None:
        d = self.graph.get_latest_variable("delta")
        rg = self.graph.bfs(d.full_node_id, "backward")
        names = {n.name for n in rg.nodes}
        self.assertIn("alpha", names)
        self.assertIn("delta", names)
        self.assertNotIn("epsilon", names)

    # ------------------------------------------------------------------
    # BFS both
    # ------------------------------------------------------------------

    def test_bfs_both_from_middle(self) -> None:
        d = self.graph.get_latest_variable("delta")
        rg = self.graph.bfs(d.full_node_id, "both")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "delta", "epsilon"})

    def test_bfs_both_from_leaf(self) -> None:
        e = self.graph.get_latest_variable("epsilon")
        rg = self.graph.bfs(e.full_node_id, "both")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "delta", "epsilon"})

    # ------------------------------------------------------------------
    # BFS with category filter
    # ------------------------------------------------------------------

    def test_bfs_forward_with_category_filter(self) -> None:
        a = self.graph.get_latest_variable("alpha")
        rg = self.graph.bfs(a.full_node_id, "forward",
                            categories=["extraction"])
        names = {n.name for n in rg.nodes}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertIn("gamma", names)
        self.assertNotIn("delta", names)
        self.assertNotIn("epsilon", names)

    def test_bfs_forward_with_single_category_string(self) -> None:
        a = self.graph.get_latest_variable("alpha")
        rg = self.graph.bfs(a.full_node_id, "forward",
                            categories="extraction")
        names = {n.name for n in rg.nodes}
        self.assertIn("beta", names)
        self.assertNotIn("delta", names)

    # ------------------------------------------------------------------
    # BFS with time filter
    # ------------------------------------------------------------------

    def test_bfs_forward_with_time_filter(self) -> None:
        a = self.graph.get_latest_variable("alpha")
        e = self.graph.get_latest_variable("epsilon")
        rg = self.graph.bfs(a.full_node_id, "forward",
                            end_time=e.created_at)
        names = {n.name for n in rg.nodes}
        self.assertIn("alpha", names)
        self.assertIn("epsilon", names)

    def test_bfs_forward_with_tight_end_time(self) -> None:
        """Only the root should survive if end_time is before other nodes."""
        a = self.graph.get_latest_variable("alpha")
        rg = self.graph.bfs(a.full_node_id, "forward",
                            end_time=a.created_at)
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha"})

    # ------------------------------------------------------------------
    # BFS with combined filters
    # ------------------------------------------------------------------

    def test_bfs_both_with_category_and_time(self) -> None:
        d = self.graph.get_latest_variable("delta")
        rg = self.graph.bfs(
            d.full_node_id, "both",
            categories=["extraction", "search"],
        )
        names = {n.name for n in rg.nodes}
        self.assertIn("delta", names)
        self.assertIn("beta", names)
        self.assertNotIn("epsilon", names)

    # ------------------------------------------------------------------
    # BFS edge cases
    # ------------------------------------------------------------------

    def test_bfs_nonexistent_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.graph.bfs("nonexistent@1", "forward")

    def test_bfs_single_node(self) -> None:
        e = self.graph.get_latest_variable("epsilon")
        rg = self.graph.bfs(e.full_node_id, "forward")
        self.assertEqual(len(rg), 1)

    # ------------------------------------------------------------------
    # Induced subgraph
    # ------------------------------------------------------------------

    def test_induced_subgraph(self) -> None:
        a = self.graph.get_latest_variable("alpha")
        d = self.graph.get_latest_variable("delta")
        e = self.graph.get_latest_variable("epsilon")
        rg = self.graph.induced_subgraph(
            [a.full_node_id, d.full_node_id, e.full_node_id]
        )
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"alpha", "delta", "epsilon"})
        for edge in rg.edges:
            self.assertIn(edge.source_full_node_id, rg)
            self.assertIn(edge.target_full_node_id, rg)

    def test_induced_subgraph_skips_missing(self) -> None:
        rg = self.graph.induced_subgraph(["nonexistent@1"])
        self.assertTrue(rg.is_empty)

    def test_induced_subgraph_generator(self) -> None:
        """Accept a generator as input."""
        gen = (n.full_node_id for n in self.graph.get_all_nodes()
               if n.name in {"alpha", "epsilon"})
        rg = self.graph.induced_subgraph(gen)
        self.assertEqual(len(rg), 2)

    # ------------------------------------------------------------------
    # filter_by_time on ExecNetwork
    # ------------------------------------------------------------------

    def test_filter_by_time_full_range(self) -> None:
        rg = self.graph.filter_by_time()
        self.assertEqual(len(rg), 5)

    def test_filter_by_time_narrow(self) -> None:
        b = self.graph.get_latest_variable("beta")
        d = self.graph.get_latest_variable("delta")
        rg = self.graph.filter_by_time(start=b.created_at, end=d.created_at)
        names = {n.name for n in rg.nodes}
        self.assertIn("beta", names)
        self.assertIn("delta", names)
        self.assertNotIn("epsilon", names)

    # ------------------------------------------------------------------
    # RuntimeGraph secondary methods
    # ------------------------------------------------------------------

    def test_runtime_graph_filter_by_category(self) -> None:
        rg = self.graph.to_runtime_graph()
        filtered = rg.filter_by_category("search")
        names = {n.name for n in filtered.nodes}
        self.assertEqual(names, {"delta"})

    def test_runtime_graph_filter_by_multi_category(self) -> None:
        rg = self.graph.to_runtime_graph()
        filtered = rg.filter_by_category({"extraction", "response"})
        names = {n.name for n in filtered.nodes}
        self.assertEqual(names, {"alpha", "beta", "gamma", "epsilon"})

    def test_runtime_graph_induced_subgraph(self) -> None:
        rg = self.graph.to_runtime_graph()
        a_id = self.graph.get_latest_variable("alpha").full_node_id
        e_id = self.graph.get_latest_variable("epsilon").full_node_id
        sub = rg.induced_subgraph([a_id, e_id])
        self.assertEqual(len(sub), 2)
        self.assertEqual(sub.edge_count, 0)

    def test_runtime_graph_get_root_and_leaf(self) -> None:
        rg = self.graph.to_runtime_graph()
        root_names = {n.name for n in rg.get_root_nodes()}
        leaf_names = {n.name for n in rg.get_leaf_nodes()}
        self.assertIn("alpha", root_names)
        self.assertIn("epsilon", leaf_names)

    def test_runtime_graph_filter_by_time(self) -> None:
        rg = self.graph.to_runtime_graph()
        a = self.graph.get_latest_variable("alpha")
        b = self.graph.get_latest_variable("beta")
        filtered = rg.filter_by_time(start=a.created_at, end=b.created_at)
        names = {n.name for n in filtered.nodes}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)

    def test_runtime_graph_time_range(self) -> None:
        rg = self.graph.to_runtime_graph()
        times = [n.created_at for n in rg.nodes]
        tr = rg.time_range()
        self.assertIsNotNone(tr)
        assert tr is not None
        self.assertEqual(tr, (min(times), max(times)))

    def test_runtime_graph_time_range_empty(self) -> None:
        empty = RuntimeGraph(nodes=[], edges=[], ops=[])
        self.assertIsNone(empty.time_range())

    # ------------------------------------------------------------------
    # export_graph / import_graph roundtrip on ExecNetwork
    # ------------------------------------------------------------------

    def test_export_import_roundtrip(self) -> None:
        exported = self.graph.export_graph()
        imported = ExecNetwork.import_graph(exported)
        self.assertEqual(imported.graph_id, self.graph.graph_id)
        self.assertEqual(imported.node_count, self.graph.node_count)
        self.assertEqual(imported.edge_count, self.graph.edge_count)
        self.assertEqual(imported.op_count, self.graph.op_count)

    # ------------------------------------------------------------------
    # to_xml / to_markdown with include_metadata
    # ------------------------------------------------------------------

    def test_to_xml_includes_created_at(self) -> None:
        rg = self.graph.to_runtime_graph()
        xml = rg.to_xml()
        self.assertIn("<created_at>", xml)
        self.assertIn("created in the system at", xml)

    def test_to_markdown_includes_created_at(self) -> None:
        rg = self.graph.to_runtime_graph()
        md = rg.to_markdown()
        self.assertIn("Created At:", md)
        self.assertIn("created in the system at", md)

    def test_to_xml_include_metadata(self) -> None:
        with comment_graph(metadata={"env": "test"}) as g:
            with comment_session(session_name="meta"):
                comment_variable(
                    "meta_val", id_strategy="content",
                    metadata={"key": "val"},
                )
            rg = g.to_runtime_graph()
            xml = rg.to_xml(include_metadata=True)
            self.assertIn("<metadata>", xml)
            self.assertIn('"key"', xml)

    def test_to_xml_no_metadata_by_default(self) -> None:
        rg = self.graph.to_runtime_graph()
        xml = rg.to_xml()
        self.assertNotIn("<metadata>", xml)

    def test_to_xml_can_hide_variable_value(self) -> None:
        with comment_graph() as g:
            with comment_session(session_name="hidden-value"):
                comment_variable(
                    "hidden variable payload",
                    variable_name="payload",
                    id_strategy="content",
                )
            rg = g.to_runtime_graph()
            xml = rg.to_xml(include_variable_value=False)
            self.assertNotIn("<value>", xml)
            self.assertNotIn("hidden variable payload", xml)

    def test_to_markdown_include_metadata(self) -> None:
        with comment_graph() as g:
            with comment_session(session_name="meta"):
                comment_variable(
                    "meta_val2", id_strategy="content",
                    metadata={"mk": "mv"},
                )
            rg = g.to_runtime_graph()
            md = rg.to_markdown(include_metadata=True)
            self.assertIn("Metadata:", md)

    def test_to_markdown_can_hide_variable_value(self) -> None:
        with comment_graph() as g:
            with comment_session(session_name="hidden-value"):
                comment_variable(
                    "hidden markdown payload",
                    variable_name="payload",
                    id_strategy="content",
                )
            rg = g.to_runtime_graph()
            md = rg.to_markdown(include_variable_value=False)
            self.assertNotIn("Value:", md)
            self.assertNotIn("hidden markdown payload", md)
