"""BFS traversal tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_link,
    comment_op,
    comment_op_scope,
    comment_session,
    comment_variable,
    enable_tracing,
)
from smartcomment.runtime.network import ExecNetwork
from tests.helpers import BaseTracingTest


class BfsBothDirectionTests(BaseTracingTest):
    """Verify that ``bfs(direction="both")`` computes the union of the
    forward cone and backward cone without leaking into sibling branches.

    Fixture graph (single session, literal identity):

        root --[op1]--> start --[op2]--> child
        root --[op1]--> sibling

    ``bfs(start, "both")`` should produce ``{root, start, child}`` but
    **not** ``sibling``, because ``sibling`` is only reachable through
    ``root``'s outgoing edges — and ``root`` was reached via the backward
    cone so it must only expand backward.

    Additionally tests cross-cone edge collection.
    """

    graph: ExecNetwork
    op1_id: str
    op2_id: str

    @classmethod
    def setUpClass(cls) -> None:
        enable_tracing()
        import time

        _id = lambda v: str(v)

        with comment_graph() as g:
            with comment_session(session_name="sess"):
                rv_root = comment_variable(
                    "root", id_strategy=_id, category="cat",
                    comment="root", to_runtime=True,
                )
                time.sleep(0.01)

                with comment_op_scope(op_name="op1", category="cat") as op1:
                    cls.op1_id = op1.op_id
                    comment_op(
                        inputs=[rv_root],
                        outputs=[
                            ("start", {"id_strategy": _id, "category": "cat"}),
                            ("sibling", {"id_strategy": _id, "category": "cat"}),
                        ],
                        op_name="op1",
                        reuse_op=True,
                    )

                time.sleep(0.01)
                rv_start = g.get_latest_variable("start")

                with comment_op_scope(op_name="op2", category="cat") as op2:
                    cls.op2_id = op2.op_id
                    comment_op(
                        inputs=[rv_start],
                        outputs=[
                            ("child", {"id_strategy": _id, "category": "cat"}),
                        ],
                        op_name="op2",
                        reuse_op=True,
                    )

            cls.graph = g

    @classmethod
    def tearDownClass(cls) -> None:
        enable_tracing()

    def test_both_excludes_sibling(self) -> None:
        """Sibling is reachable through root's outgoing but not via start's cones."""
        start = self.graph.get_latest_variable("start")
        rg = self.graph.bfs(start.full_node_id, "both")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"root", "start", "child"})
        self.assertNotIn("sibling", names)

    def test_forward_only(self) -> None:
        start = self.graph.get_latest_variable("start")
        rg = self.graph.bfs(start.full_node_id, "forward")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "child"})

    def test_backward_only(self) -> None:
        start = self.graph.get_latest_variable("start")
        rg = self.graph.bfs(start.full_node_id, "backward")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"root", "start"})

    def test_both_includes_cross_cone_edges(self) -> None:
        """Edges between backward-cone and forward-cone nodes are included."""
        start = self.graph.get_latest_variable("start")
        rg = self.graph.bfs(start.full_node_id, "both")
        edge_pairs = {
            (e.source_full_node_id, e.target_full_node_id) for e in rg.edges
        }
        root_id = self.graph.get_latest_variable("root").full_node_id
        child_id = self.graph.get_latest_variable("child").full_node_id
        self.assertIn((root_id, start.full_node_id), edge_pairs)
        self.assertIn((start.full_node_id, child_id), edge_pairs)

    def test_both_from_root_includes_all(self) -> None:
        """From root, backward cone is empty but forward cone reaches everything."""
        root = self.graph.get_latest_variable("root")
        rg = self.graph.bfs(root.full_node_id, "both")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"root", "start", "sibling", "child"})

    def test_both_from_leaf_excludes_sibling(self) -> None:
        """From child, backward reaches start and root; forward is empty."""
        child = self.graph.get_latest_variable("child")
        rg = self.graph.bfs(child.full_node_id, "both")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"root", "start", "child"})
        self.assertNotIn("sibling", names)

    def test_both_with_max_depth_1(self) -> None:
        """max_depth=1 limits both directions to direct neighbours only."""
        start = self.graph.get_latest_variable("start")
        rg = self.graph.bfs(start.full_node_id, "both", max_depth=1)
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"root", "start", "child"})



class BfsSiblingInputsTests(BaseTracingTest):
    """Verify ``bfs(include_sibling_inputs=True)`` semantics.

    The default forward BFS misses co-inputs of ops it traverses: if op ``O``
    produces ``t`` from ``(s, p)`` and only ``s`` is forward-reachable from
    the starting node, ``p`` and the edge ``p -> t`` silently drop out of
    the result even though they were part of the same operation that created
    ``t``. ``include_sibling_inputs=True`` pulls those co-inputs back in as
    *boundary* nodes that appear in the subgraph but are not themselves
    expanded along their other outgoing edges. These tests pin down that
    rule along with its interaction with filters, ``max_depth``, the
    ``both`` direction, the sentinel operation, and boundary promotion.
    """

    @staticmethod
    def _literal_id(value):
        return str(value)

    # ------------------------------------------------------------------
    # Core behaviour: sibling input is pulled in, and only one hop
    # ------------------------------------------------------------------

    def _build_basic_graph(self):
        """Build:

            start --[op_A]--> merged --[op_B]--> leaf
            pco   --[op_A]--> merged
            pco   --[op_C]--> orphan

        ``pco`` is a co-input to op_A with ``start`` but is not itself
        forward-reachable from ``start``. ``orphan`` is another output of
        ``pco`` via an unrelated op_C and must never appear in a forward
        search rooted at ``start`` with sibling inputs enabled, because
        boundary nodes do not expand.
        """
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_start = comment_variable(
                    "start", id_strategy=_id, to_runtime=True,
                )
                rv_pco = comment_variable(
                    "pco", id_strategy=_id, to_runtime=True,
                )
                with comment_op_scope(op_name="op_A"):
                    comment_op(
                        inputs=[rv_start, rv_pco],
                        outputs=[("merged", {"id_strategy": _id})],
                        op_name="op_A",
                        reuse_op=True,
                    )
                rv_merged = g.get_latest_variable("merged")
                with comment_op_scope(op_name="op_B"):
                    comment_op(
                        inputs=[rv_merged],
                        outputs=[("leaf", {"id_strategy": _id})],
                        op_name="op_B",
                        reuse_op=True,
                    )
                with comment_op_scope(op_name="op_C"):
                    comment_op(
                        inputs=[rv_pco],
                        outputs=[("orphan", {"id_strategy": _id})],
                        op_name="op_C",
                        reuse_op=True,
                    )
        return g

    def test_without_sibling_inputs_omits_co_parent(self) -> None:
        """Baseline: the default forward BFS silently drops sibling inputs."""
        g = self._build_basic_graph()
        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "forward")
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "merged", "leaf"})
        self.assertNotIn("pco", names)

    def test_with_sibling_inputs_adds_co_parent(self) -> None:
        """Enabling the flag adds the co-input and the sibling edge."""
        g = self._build_basic_graph()
        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "forward", include_sibling_inputs=True)
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "merged", "leaf", "pco"})
        # The sibling edge pco -> merged is present.
        self.assertTrue(any(
            e.source_full_node_id == g.get_latest_variable("pco").full_node_id
            and e.target_full_node_id == g.get_latest_variable("merged").full_node_id
            for e in rg.edges
        ))

    def test_boundary_node_does_not_expand_other_children(self) -> None:
        """Gap C contract: ``orphan`` (pco's other child) must stay out."""
        g = self._build_basic_graph()
        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "forward", include_sibling_inputs=True)
        names = {n.name for n in rg.nodes}
        self.assertNotIn("orphan", names)
        # op_C edges are never collected, so op_C is absent from visited_ops.
        op_names = {op.op_name for op in rg.ops}
        self.assertIn("op_A", op_names)
        self.assertIn("op_B", op_names)
        self.assertNotIn("op_C", op_names)

    # ------------------------------------------------------------------
    # Gap C: boundary -> interior upgrade via a later forward path
    # ------------------------------------------------------------------

    def test_boundary_is_upgraded_when_reached_by_forward_path(self) -> None:
        """A boundary node promoted by a later primary edge must expand.

        Fixture:

            start --[op_A]--> merged
            pco   --[op_A]--> merged
            merged --[op_D]--> pco
            pco --[op_C]--> orphan

        ``pco`` enters the result first as a boundary node via sibling
        expansion at ``merged``. Then the main BFS traverses
        ``merged -> pco`` and must upgrade ``pco`` to interior and expand
        it, bringing ``orphan`` into the result.
        """
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_start = comment_variable(
                    "start", id_strategy=_id, to_runtime=True,
                )
                rv_pco = comment_variable(
                    "pco", id_strategy=_id, to_runtime=True,
                )
                with comment_op_scope(op_name="op_A"):
                    comment_op(
                        inputs=[rv_start, rv_pco],
                        outputs=[("merged", {"id_strategy": _id})],
                        op_name="op_A",
                        reuse_op=True,
                    )
                rv_merged = g.get_latest_variable("merged")
                with comment_op_scope(op_name="op_D"):
                    comment_op(
                        inputs=[rv_merged],
                        outputs=[rv_pco],
                        op_name="op_D",
                        reuse_op=True,
                    )
                with comment_op_scope(op_name="op_C"):
                    comment_op(
                        inputs=[rv_pco],
                        outputs=[("orphan", {"id_strategy": _id})],
                        op_name="op_C",
                        reuse_op=True,
                    )

        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "forward", include_sibling_inputs=True)
        names = {n.name for n in rg.nodes}
        self.assertIn("pco", names)
        self.assertIn("orphan", names)
        op_names = {op.op_name for op in rg.ops}
        self.assertIn("op_C", op_names)

    def test_max_depth_blocks_boundary_upgrade_beyond_limit(self) -> None:
        """Upgrade still obeys ``max_depth``: out-of-budget siblings stay boundary.

        Same fixture as the previous test but with ``max_depth=1``: the
        primary walk only reaches ``merged``; ``merged -> pco`` is at
        depth 2 and blocked, so ``pco`` must remain a boundary node and
        ``orphan`` must not appear.
        """
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_start = comment_variable(
                    "start", id_strategy=_id, to_runtime=True,
                )
                rv_pco = comment_variable(
                    "pco", id_strategy=_id, to_runtime=True,
                )
                with comment_op_scope(op_name="op_A"):
                    comment_op(
                        inputs=[rv_start, rv_pco],
                        outputs=[("merged", {"id_strategy": _id})],
                        op_name="op_A",
                        reuse_op=True,
                    )
                rv_merged = g.get_latest_variable("merged")
                with comment_op_scope(op_name="op_D"):
                    comment_op(
                        inputs=[rv_merged],
                        outputs=[rv_pco],
                        op_name="op_D",
                        reuse_op=True,
                    )
                with comment_op_scope(op_name="op_C"):
                    comment_op(
                        inputs=[rv_pco],
                        outputs=[("orphan", {"id_strategy": _id})],
                        op_name="op_C",
                        reuse_op=True,
                    )

        start = g.get_latest_variable("start")
        rg = g.bfs(
            start.full_node_id,
            "forward",
            max_depth=1,
            include_sibling_inputs=True,
        )
        names = {n.name for n in rg.nodes}
        self.assertIn("pco", names)  # added as boundary via sibling expansion
        self.assertNotIn("orphan", names)  # upgrade was blocked by max_depth

    # ------------------------------------------------------------------
    # Gap D: filter semantics apply strictly to boundary nodes
    # ------------------------------------------------------------------

    def test_category_filter_excludes_boundary_node(self) -> None:
        """A co-input outside the category filter must be skipped."""
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_start = comment_variable(
                    "start",
                    id_strategy=_id,
                    category="main",
                    to_runtime=True,
                )
                rv_pco = comment_variable(
                    "pco",
                    id_strategy=_id,
                    category="extra",
                    to_runtime=True,
                )
                with comment_op_scope(op_name="op_A"):
                    comment_op(
                        inputs=[rv_start, rv_pco],
                        outputs=[(
                            "merged",
                            {"id_strategy": _id, "category": "main"},
                        )],
                        op_name="op_A",
                        reuse_op=True,
                    )

        start = g.get_latest_variable("start")
        rg = g.bfs(
            start.full_node_id,
            "forward",
            categories="main",
            include_sibling_inputs=True,
        )
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "merged"})
        self.assertNotIn("pco", names)

    # ------------------------------------------------------------------
    # Sentinel op never triggers sibling expansion
    # ------------------------------------------------------------------

    def test_sentinel_op_also_triggers_sibling_expansion(self) -> None:
        """Sentinel-op edges are treated uniformly by sibling expansion.

        ``comment_link`` outside any ``comment_op_scope`` emits edges
        under the per-graph sentinel operation identifier. The BFS does
        not special-case that identifier: every forward edge, sentinel
        or not, triggers sibling expansion on its target. This gives
        callers a predictable rule ("same op_id on target means sibling
        input"), at the cost of conflating unrelated ``comment_link``
        calls that happen to target the same node.
        """
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_start = comment_variable(
                    "start", id_strategy=_id, to_runtime=True,
                )
                rv_other = comment_variable(
                    "other", id_strategy=_id, to_runtime=True,
                )
                rv_sink = comment_variable(
                    "sink", id_strategy=_id, to_runtime=True,
                )
                comment_link(source=rv_start, target=rv_sink)
                comment_link(source=rv_other, target=rv_sink)

        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "forward", include_sibling_inputs=True)
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "sink", "other"})

    # ------------------------------------------------------------------
    # Gap E: ``direction="both"`` forward half also gets siblings;
    # ``direction="backward"`` is unaffected.
    # ------------------------------------------------------------------

    def test_both_direction_forward_half_gets_siblings(self) -> None:
        """``direction="both"`` must apply sibling expansion on its forward arm.

        Fixture adds a backward ancestor so ``both`` is distinguishable:

            ancestor --[op_Z]--> start --[op_A]--> merged
            pco --[op_A]--> merged
        """
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_anc = comment_variable(
                    "ancestor", id_strategy=_id, to_runtime=True,
                )
                with comment_op_scope(op_name="op_Z"):
                    comment_op(
                        inputs=[rv_anc],
                        outputs=[("start", {"id_strategy": _id})],
                        op_name="op_Z",
                        reuse_op=True,
                    )
                rv_start = g.get_latest_variable("start")
                rv_pco = comment_variable(
                    "pco", id_strategy=_id, to_runtime=True,
                )
                with comment_op_scope(op_name="op_A"):
                    comment_op(
                        inputs=[rv_start, rv_pco],
                        outputs=[("merged", {"id_strategy": _id})],
                        op_name="op_A",
                        reuse_op=True,
                    )

        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "both", include_sibling_inputs=True)
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"ancestor", "start", "merged", "pco"})

    def test_backward_direction_ignores_include_sibling_inputs(self) -> None:
        """Backward BFS is unaffected by the sibling flag.

        Backward traversal already walks every incoming edge, so the
        flag has no work to do. The result must be identical to the
        backward search without the flag.
        """
        g = self._build_basic_graph()
        leaf = g.get_latest_variable("leaf")
        rg_with = g.bfs(
            leaf.full_node_id, "backward", include_sibling_inputs=True,
        )
        rg_without = g.bfs(leaf.full_node_id, "backward")
        self.assertEqual(
            {n.name for n in rg_with.nodes},
            {n.name for n in rg_without.nodes},
        )
        self.assertEqual(
            {e.edge_id for e in rg_with.edges},
            {e.edge_id for e in rg_without.edges},
        )

    # ------------------------------------------------------------------
    # Boundary nodes do not expand: edges whose source is a boundary
    # node are intentionally excluded from the result.
    # ------------------------------------------------------------------

    def test_inter_boundary_edge_is_not_collected(self) -> None:
        """An edge between two boundary nodes is NOT added to the result.

        Fixture:

            start --[op_A]--> merged
            pco1 --[op_A]--> merged
            pco2 --[op_A]--> merged
            pco1 --[op_Z]--> pco2

        The first three edges drag both ``pco1`` and ``pco2`` in as
        boundary nodes. The ``pco1 -> pco2`` edge has boundary ``pco1``
        as its source; boundary nodes do not expand their other
        outgoing edges, so this edge is deliberately left out. This
        keeps the flag's semantics as "one hop of same-op co-inputs
        per traversed forward edge" and avoids cascading sibling
        expansion through boundary nodes. Consequently, op_Z is not
        exposed either: it had no edge incident to an interior node.
        """
        enable_tracing()
        _id = self._literal_id
        with comment_graph() as g:
            with comment_session(session_name="s"):
                rv_start = comment_variable(
                    "start", id_strategy=_id, to_runtime=True,
                )
                rv_pco1 = comment_variable(
                    "pco1", id_strategy=_id, to_runtime=True,
                )
                rv_pco2 = comment_variable(
                    "pco2", id_strategy=_id, to_runtime=True,
                )
                with comment_op_scope(op_name="op_A"):
                    comment_op(
                        inputs=[rv_start, rv_pco1, rv_pco2],
                        outputs=[("merged", {"id_strategy": _id})],
                        op_name="op_A",
                        reuse_op=True,
                    )
                with comment_op_scope(op_name="op_Z"):
                    comment_op(
                        inputs=[rv_pco1],
                        outputs=[rv_pco2],
                        op_name="op_Z",
                        reuse_op=True,
                    )

        start = g.get_latest_variable("start")
        rg = g.bfs(start.full_node_id, "forward", include_sibling_inputs=True)
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "merged", "pco1", "pco2"})

        pco1_id = g.get_latest_variable("pco1").full_node_id
        pco2_id = g.get_latest_variable("pco2").full_node_id
        self.assertFalse(any(
            e.source_full_node_id == pco1_id and e.target_full_node_id == pco2_id
            for e in rg.edges
        ))
        op_names = {op.op_name for op in rg.ops}
        self.assertNotIn("op_Z", op_names)

    # ------------------------------------------------------------------
    # op_ids filter interaction
    # ------------------------------------------------------------------

    def test_op_ids_filter_limits_sibling_expansion(self) -> None:
        """Ops outside the ``op_ids`` filter neither traverse nor sibling-expand.

        With ``op_ids={op_A}``, op_B and op_C never contribute edges, and
        sibling expansion only runs for op_A.
        """
        g = self._build_basic_graph()
        start = g.get_latest_variable("start")
        # Locate op_A's identifier in the graph.
        op_A_id = next(
            op.op_id for op in g.get_all_operations() if op.op_name == "op_A"
        )
        rg = g.bfs(
            start.full_node_id,
            "forward",
            op_ids=op_A_id,
            include_sibling_inputs=True,
        )
        names = {n.name for n in rg.nodes}
        self.assertEqual(names, {"start", "merged", "pco"})
        op_names = {op.op_name for op in rg.ops}
        self.assertEqual(op_names, {"op_A"})
