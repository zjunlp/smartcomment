"""Session storage and provenance tests."""

from __future__ import annotations

from smartcomment import (
    IdentityRegistry,
    comment_graph,
    comment_op,
    comment_op_scope,
    comment_session,
    comment_variable,
    enable_tracing,
)
from smartcomment.runtime.network import ExecNetwork, none_session_id
from smartcomment.runtime.session import RuntimeSession
from smartcomment.runtime.variable import RuntimeVariable
from tests.helpers import (
    BaseTracingTest,
    MemoryItem,
)


class SessionStorageTests(BaseTracingTest):
    """Test session persistence in the graph driver and session-related queries."""

    def setUp(self) -> None:
        enable_tracing()
        IdentityRegistry.register(
            MemoryItem,
            lambda item: f"mem-{item.memory_id}",
            exist_ok=True,
        )

    def _build_cross_session_graph(self) -> ExecNetwork:
        """Build a graph with two sessions linked by a cross-session operation.

        Session "s1" creates variable A.
        Session "s2" uses A as input and produces variable B.
        """
        with comment_graph() as graph:
            with comment_session(session_id="s1", session_name="session-one"):
                a = comment_variable("alpha", id_strategy="content", comment="root", to_runtime=True)

            with comment_session(session_id="s2", session_name="session-two"):
                b_val = "beta"
                comment_op(
                    inputs=[a],
                    outputs=[(b_val, {"id_strategy": "content"})],
                    op_name="transform",
                )
        return graph

    def test_session_persisted_after_comment_session(self) -> None:
        """Sessions created via comment_session are stored in the driver."""
        with comment_graph() as graph:
            with comment_session(session_id="sid-1", session_name="first"):
                pass
            with comment_session(session_id="sid-2", session_name="second"):
                pass

        sessions = graph.get_all_sessions()
        self.assertEqual(len(sessions), 2)
        ids = {s.session_id for s in sessions}
        self.assertEqual(ids, {"sid-1", "sid-2"})

    def test_auto_session_persisted_from_comment_op_scope(self) -> None:
        """Auto-created sessions from comment_op_scope are stored."""
        with comment_graph() as graph:
            with comment_op_scope(op_name="auto-op"):
                pass

        sessions = graph.get_all_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].category, "session")

    def test_get_session_by_id(self) -> None:
        """Retrieve a session by its identifier."""
        with comment_graph() as graph:
            with comment_session(session_id="lookup-test", session_name="Lookup"):
                pass

        session = graph.get_session("lookup-test")
        self.assertIsInstance(session, RuntimeSession)
        self.assertEqual(session.session_name, "Lookup")

    def test_get_session_raises_on_missing(self) -> None:
        """ExecNetworkKeyError raised for unknown session id."""
        from smartcomment.runtime.errors import ExecNetworkKeyError

        with comment_graph() as graph:
            pass
        with self.assertRaises(ExecNetworkKeyError):
            graph.get_session("nonexistent")

    def test_filter_by_session_single(self) -> None:
        """filter_by_session returns nodes belonging to the given session."""
        graph = self._build_cross_session_graph()
        sg = graph.filter_by_session("s1")
        node_sessions = {n.session_id for n in sg.nodes}
        self.assertTrue(node_sessions.issubset({"s1"}))
        self.assertGreater(len(sg.nodes), 0)

    def test_filter_by_session_multiple(self) -> None:
        """filter_by_session accepts an iterable of session ids."""
        graph = self._build_cross_session_graph()
        sg = graph.filter_by_session(["s1", "s2"])
        node_sessions = {n.session_id for n in sg.nodes}
        self.assertTrue(node_sessions.issubset({"s1", "s2"}))
        self.assertGreaterEqual(len(sg.nodes), 2)

    def test_contributing_sessions_returns_runtime_sessions(self) -> None:
        """contributing_sessions returns list[RuntimeSession] sorted by created_at."""
        graph = self._build_cross_session_graph()

        content_fn = IdentityRegistry.get("content")
        b_rv = graph.get_latest_variable(content_fn("beta"))
        sessions = graph.contributing_sessions(b_rv.full_node_id)

        self.assertIsInstance(sessions, list)
        self.assertTrue(all(isinstance(s, RuntimeSession) for s in sessions))
        session_ids = [s.session_id for s in sessions]
        self.assertIn("s1", session_ids)
        self.assertIn("s2", session_ids)

        timestamps = [s.created_at for s in sessions]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_get_ancestors_returns_sorted_variables(self) -> None:
        """get_ancestors returns deduplicated list[RuntimeVariable] sorted by created_at."""
        graph = self._build_cross_session_graph()

        content_fn = IdentityRegistry.get("content")
        b_rv = graph.get_latest_variable(content_fn("beta"))
        ancestors = graph.get_ancestors(b_rv.full_node_id)

        self.assertIsInstance(ancestors, list)
        self.assertTrue(all(isinstance(v, RuntimeVariable) for v in ancestors))
        self.assertGreater(len(ancestors), 0)

        ancestor_ids = {v.full_node_id for v in ancestors}
        self.assertNotIn(b_rv.full_node_id, ancestor_ids)

        timestamps = [v.created_at for v in ancestors]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_get_descendants_returns_sorted_variables(self) -> None:
        """get_descendants returns deduplicated list[RuntimeVariable] sorted by created_at."""
        graph = self._build_cross_session_graph()

        content_fn = IdentityRegistry.get("content")
        a_rv = graph.get_latest_variable(content_fn("alpha"))
        descendants = graph.get_descendants(a_rv.full_node_id)

        self.assertIsInstance(descendants, list)
        self.assertTrue(all(isinstance(v, RuntimeVariable) for v in descendants))
        self.assertGreater(len(descendants), 0)

        descendant_ids = {v.full_node_id for v in descendants}
        self.assertNotIn(a_rv.full_node_id, descendant_ids)

        timestamps = [v.created_at for v in descendants]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_get_downstream_sessions(self) -> None:
        """get_downstream_sessions returns list[RuntimeSession] sorted by created_at."""
        graph = self._build_cross_session_graph()

        content_fn = IdentityRegistry.get("content")
        a_rv = graph.get_latest_variable(content_fn("alpha"))
        ds_sessions = graph.get_downstream_sessions(a_rv.full_node_id)

        self.assertIsInstance(ds_sessions, list)
        self.assertTrue(all(isinstance(s, RuntimeSession) for s in ds_sessions))
        session_ids = [s.session_id for s in ds_sessions]
        self.assertIn("s2", session_ids)

        timestamps = [s.created_at for s in ds_sessions]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_bfs_with_session_filter(self) -> None:
        """BFS respects the session_ids filter parameter."""
        graph = self._build_cross_session_graph()

        content_fn = IdentityRegistry.get("content")
        a_rv = graph.get_latest_variable(content_fn("alpha"))

        sg_filtered = graph.bfs(
            a_rv.full_node_id,
            direction="forward",
            session_ids="s1",
        )
        for node in sg_filtered.nodes:
            if node.full_node_id != a_rv.full_node_id:
                self.assertEqual(node.session_id, "s1")

    def test_session_count_property(self) -> None:
        """session_count reflects the number of persisted sessions."""
        with comment_graph() as graph:
            self.assertEqual(graph.session_count, 0)
            with comment_session(session_id="sc-1"):
                pass
            self.assertEqual(graph.session_count, 1)
            with comment_session(session_id="sc-2"):
                pass
            self.assertEqual(graph.session_count, 2)

    def test_export_import_roundtrip_includes_sessions(self) -> None:
        """Sessions survive export_graph / import_graph round-trip."""
        with comment_graph() as graph:
            with comment_session(session_id="rt-sess", session_name="round-trip"):
                comment_variable("roundtrip-val", id_strategy="content")

        data = graph.export_graph()
        restored = ExecNetwork.import_graph(data)

        self.assertEqual(restored.session_count, 1)
        s = restored.get_session("rt-sess")
        self.assertEqual(s.session_name, "round-trip")

    def test_add_session_via_exec_network(self) -> None:
        """add_session on ExecNetwork stores a RuntimeSession."""
        from smartcomment.schema.session import Session

        with comment_graph() as graph:
            raw = Session(
                session_id="manual-s",
                session_name="Manual",
                graph_id=graph.graph_id,
                filename=__file__,
                lineno=0,
            )
            rs = RuntimeSession(session=raw)
            graph.add_session(rs)

        self.assertEqual(graph.session_count, 1)
        retrieved = graph.get_session("manual-s")
        self.assertEqual(retrieved.session_name, "Manual")

    def test_add_session_via_exec_network_rejects_none_sentinel_session_id(self) -> None:
        """add_session rejects user sessions with the reserved NONE session id."""
        from smartcomment.schema.session import Session

        with comment_graph() as graph:
            raw = Session(
                session_id=none_session_id(),
                session_name="ShouldFail",
                graph_id=graph.graph_id,
                filename=__file__,
                lineno=0,
            )
            rs = RuntimeSession(session=raw)
            with self.assertRaises(ValueError) as cm:
                graph.add_session(rs)
        self.assertIn(none_session_id(), str(cm.exception))

    def test_add_operation_via_exec_network_rejects_none_sentinel_op_id(self) -> None:
        """add_operation rejects user operations with the reserved NONE op id."""
        from smartcomment.runtime.network import none_op_id
        from smartcomment.runtime.operation import RuntimeOp
        from smartcomment.schema.operation import OpRecord

        with comment_graph() as graph:
            raw = OpRecord(
                op_id=none_op_id(),
                graph_id=graph.graph_id,
                session_id="fake",
                op_name="ShouldFail",
                filename=__file__,
                lineno=0,
            )
            ro = RuntimeOp(op=raw)
            with self.assertRaises(ValueError) as cm:
                graph.add_operation(ro)
        self.assertIn(none_op_id(), str(cm.exception))

    def test_remove_session(self) -> None:
        """remove_session deletes a session from the graph."""
        with comment_graph() as graph:
            with comment_session(session_id="del-me"):
                pass
        self.assertEqual(graph.session_count, 1)
        graph.remove_session("del-me")
        self.assertEqual(graph.session_count, 0)

    def test_get_ancestors_and_descendants_symmetry(self) -> None:
        """Descendants of root include nodes that list root as ancestor."""
        graph = self._build_cross_session_graph()
        content_fn = IdentityRegistry.get("content")
        a_rv = graph.get_latest_variable(content_fn("alpha"))
        b_rv = graph.get_latest_variable(content_fn("beta"))

        descendants_of_a = graph.get_descendants(a_rv.full_node_id)
        ancestors_of_b = graph.get_ancestors(b_rv.full_node_id)

        desc_ids = {v.full_node_id for v in descendants_of_a}
        anc_ids = {v.full_node_id for v in ancestors_of_b}

        self.assertIn(b_rv.full_node_id, desc_ids)
        self.assertIn(a_rv.full_node_id, anc_ids)
