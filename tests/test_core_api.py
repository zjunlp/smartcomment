"""Core API tests for smartcomment."""

from __future__ import annotations

from smartcomment import (
    IdentityRegistry,
    comment_fn,
    comment_graph,
    comment_mutation,
    comment_op,
    comment_session,
    comment_variable,
    current_graph,
    disable_tracing,
)
from smartcomment.runtime.network import none_session_id
from smartcomment.runtime.variable import RuntimeVariable
from tests.helpers import (
    BaseTracingTest,
    MemoryItem,
)


class SmartcommentTests(BaseTracingTest):
    """Exercise the refactored smartcomment API surface."""

    # ------------------------------------------------------------------
    # Regression tests (rewritten from old trace_* API)
    # ------------------------------------------------------------------

    def test_comment_variable_and_operation_export_graph(self) -> None:
        """Record a basic operation and verify the exported graph shape."""
        with comment_graph() as graph:
            with comment_session(session_name="session-a") as session:
                left = "hello"
                right = "world"
                comment_variable(left, id_strategy="content", comment="Left operand.")
                comment_variable(right, id_strategy="content", comment="Right operand.")

                output = f"{left} {right}"
                comment_op(
                    inputs=[left, right],
                    outputs=[output],
                    op_name="concat",
                    comment="Concatenate two strings.",
                    id_strategy="content",
                )

                exported = graph.export_graph()

        nodes = exported["data"]["nodes"]
        ops = exported["data"]["operations"]
        edges = exported["data"]["edges"]
        self.assertEqual(len(nodes), 3)
        self.assertEqual(len(ops), 1)
        self.assertEqual(len(edges), 2)
        self.assertEqual(ops[0]["op_name"], "concat")
        self.assertIsNone(current_graph())

    def test_comment_mutation_creates_new_version(self) -> None:
        """Create a new node version when a tracked object is mutated."""
        item = MemoryItem(memory_id="mem-1", content="before")
        with comment_graph() as graph:
            with comment_session(session_name="session-a") as session:
                comment_variable(item, comment="Tracked memory item.")
                with comment_mutation(
                    target=item,
                    mutation_comment="Update memory item in place.",
                    mutation_category="memory_update",
                ) as scope:
                    item.content = "after"
                new_rv = scope.result

                versions = graph.get_versions(new_rv.full_name)

        self.assertIsNotNone(new_rv)
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].version, 1)
        self.assertEqual(versions[1].version, 2)

    def test_adapter_events_support_cross_session_provenance(self) -> None:
        """Preserve upstream session provenance through operations."""
        mem_id_fn = lambda v: v.memory_id

        with comment_graph() as graph:
            with comment_session(session_id="learning-session") as _:
                retrieved = MemoryItem(memory_id="mem-3", content="User likes tea.")
                comment_variable(retrieved, comment="Learned memory")

            with comment_session(session_id="work-session") as _:
                answer = "The user likes tea."
                # Use per-item config so MemoryItem uses its registered strategy
                # while the answer string uses the content strategy
                comment_op(
                    inputs=[(retrieved, {"id_strategy": mem_id_fn})],
                    outputs=[(answer, {"id_strategy": "content"})],
                    op_name="use_memory",
                    comment="Use the retrieved memory to answer.",
                )

                content_fn = IdentityRegistry.get("content")
                answer_rv = graph.get_latest_variable(content_fn(answer))
                sessions = graph.contributing_sessions(answer_rv.full_node_id)

        session_ids = {s.session_id for s in sessions}
        self.assertIn("learning-session", session_ids)

    def test_disable_tracing_is_effectively_no_op(self) -> None:
        """Return no graph output when tracing is globally disabled."""
        disable_tracing()
        with comment_graph() as graph:
            self.assertIsNone(graph)
            value = "hello"
            result = comment_variable(value)
            self.assertEqual(result, value)
            comment_op(
                inputs=[value],
                outputs=["world"],
                op_name="noop",
                comment="No-op while tracing is disabled.",
            )

        self.assertIsNone(current_graph())

    def test_comment_op_with_id_strategy(self) -> None:
        """comment_op resolves nodes using the provided id_strategy."""
        mem_strategy = lambda v: f"mem-{v['id']}" if isinstance(v, dict) else repr(v)

        with comment_graph() as graph:
            with comment_session(session_name="session-strategy") as _:
                mem_a = {"id": "uuid-A", "text": "hello"}
                mem_b = {"id": "uuid-B", "text": "world"}

                comment_variable(mem_a, id_strategy=mem_strategy)
                comment_variable(mem_b, id_strategy=mem_strategy)

                comment_op(
                    inputs=[mem_a],
                    outputs=[mem_b],
                    op_name="link",
                    comment="Link two memories.",
                    id_strategy=mem_strategy,
                )

                exported = graph.export_graph()

        nodes = exported["data"]["nodes"]
        node_ids = {n["name"] for n in nodes}
        self.assertIn("mem-uuid-A", node_ids)
        self.assertIn("mem-uuid-B", node_ids)

    # ------------------------------------------------------------------
    # New tests for refactored features
    # ------------------------------------------------------------------

    def test_composable_context_managers(self) -> None:
        """Verify that comment_graph/session/op compose and restore correctly."""
        self.assertIsNone(current_graph())

        with comment_graph(user_id="u1") as graph:
            self.assertIsNotNone(current_graph())
            self.assertEqual(graph.user_id, "u1")

            with comment_session(session_name="s1") as s1:
                self.assertEqual(s1.graph_id, graph.graph_id)
                rv = comment_variable("data", id_strategy="content", to_runtime=True)
                self.assertIsInstance(rv, RuntimeVariable)

            with comment_session(session_name="s2") as s2:
                self.assertNotEqual(s1.session_id, s2.session_id)

        self.assertIsNone(current_graph())

    def test_none_sentinel_for_empty_outputs(self) -> None:
        """Operations with empty outputs auto-inject the NONE sentinel."""
        with comment_graph() as graph:
            with comment_session(session_name="test") as _:
                comment_op(
                    inputs=["data_to_delete"],
                    outputs=[],
                    op_name="delete",
                    comment="Delete operation",
                    id_strategy="content",
                )

                exported = graph.export_graph()

        edges = exported["data"]["edges"]
        self.assertTrue(len(edges) > 0)
        # At least one edge should target the NONE sentinel
        targets = {e["target_full_node_id"] for e in edges}
        self.assertTrue(
            any("COMMENT:NONE" in t for t in targets),
            f"Expected NONE sentinel in targets: {targets}",
        )

    def test_none_session_id_helper(self) -> None:
        """none_session_id exposes the reserved sentinel session identifier."""
        self.assertEqual(none_session_id(), "__none__")

    def test_comment_session_rejects_reserved_none_session_id(self) -> None:
        """User-created sessions cannot use the reserved NONE sentinel session id."""
        with comment_graph() as _:
            with self.assertRaises(ValueError) as cm:
                with comment_session(session_id=none_session_id()):
                    pass
        self.assertIn(none_session_id(), str(cm.exception))

    def test_comment_op_subsumes_comment_variable(self) -> None:
        """comment_op auto-creates variables for raw value inputs."""
        with comment_graph() as graph:
            with comment_session(session_name="test") as _:
                result = comment_op(
                    inputs=["raw_input_1", "raw_input_2"],
                    outputs=["raw_output"],
                    op_name="transform",
                    id_strategy="content",
                )

                exported = graph.export_graph()

        nodes = exported["data"]["nodes"]
        # 3 unique values -> 3 nodes
        self.assertEqual(len(nodes), 3)

    def test_per_item_config_dict_in_comment_op(self) -> None:
        """Per-item (value, config_dict) tuples override shared defaults."""
        custom_strategy = lambda v: f"custom-{hash(v) % 1000}"

        with comment_graph() as graph:
            with comment_session(session_name="test") as _:
                comment_op(
                    inputs=[
                        ("input_a", {"id_strategy": custom_strategy}),
                        "input_b",
                    ],
                    outputs=["output"],
                    op_name="mixed",
                    id_strategy="content",
                )

                exported = graph.export_graph()

        nodes = exported["data"]["nodes"]
        names = {n["name"] for n in nodes}
        # input_a should use the custom strategy (custom-XXX format)
        self.assertTrue(
            any(n.startswith("custom-") for n in names),
            f"Expected a custom-* name in {names}",
        )

    def test_comment_fn_decorator(self) -> None:
        """comment_fn decorator auto-traces function inputs and outputs."""

        @comment_fn(
            op_name="test.uppercase",
            category="transform",
            id_strategy={"text": "content"},
        )
        def uppercase(text: str, repeat: int = 1) -> str:
            return text.upper() * repeat

        with comment_graph() as graph:
            with comment_session(session_name="decorator-test") as _:
                result = uppercase("hello", repeat=2)

                self.assertEqual(result, "HELLOHELLO")
                exported = graph.export_graph()

        nodes = exported["data"]["nodes"]
        ops = exported["data"]["operations"]
        edges = exported["data"]["edges"]

        self.assertTrue(len(ops) >= 1)
        self.assertEqual(ops[0]["op_name"], "test.uppercase")
        self.assertTrue(len(nodes) >= 2)
        self.assertTrue(len(edges) >= 1)

    def test_comment_fn_no_context_is_transparent(self) -> None:
        """comment_fn is transparent when no graph context is active."""

        @comment_fn(op_name="test.noop")
        def add(a: int, b: int) -> int:
            return a + b

        result = add(3, 4)
        self.assertEqual(result, 7)

    # ------------------------------------------------------------------
    # Self-loop prevention
    # ------------------------------------------------------------------

    def test_same_value_in_inputs_and_outputs_creates_new_version(self) -> None:
        """An op with the same value in inputs and outputs must bump the
        version instead of producing a self-loop edge."""
        mem = MemoryItem(memory_id="mem-loop", content="unchanged")

        with comment_graph() as graph:
            with comment_session(session_name="s") as _:
                comment_variable(mem, id_strategy=lambda m: m.memory_id)

                comment_op(
                    inputs=[(mem, {"id_strategy": lambda m: m.memory_id})],
                    outputs=[(mem, {"id_strategy": lambda m: m.memory_id})],
                    op_name="passthrough",
                    comment="Same value in and out.",
                )

        exported = graph.export_graph()
        nodes = exported["data"]["nodes"]
        edges = exported["data"]["edges"]

        mem_nodes = [n for n in nodes if n["name"] == "mem-loop"]
        self.assertEqual(len(mem_nodes), 2, "Expected v1 and v2")
        versions = sorted(n["version"] for n in mem_nodes)
        self.assertEqual(versions, [1, 2])

        for edge in edges:
            self.assertNotEqual(
                edge["source_full_node_id"],
                edge["target_full_node_id"],
                f"Self-loop detected: {edge['source_full_node_id']}",
            )

    def test_no_false_version_bump_for_disjoint_inputs_outputs(self) -> None:
        """When inputs and outputs are disjoint, no extra version is created."""
        with comment_graph() as graph:
            with comment_session(session_name="s") as _:
                comment_op(
                    inputs=["alpha"],
                    outputs=["beta"],
                    op_name="transform",
                    id_strategy="content",
                )

        exported = graph.export_graph()
        nodes = exported["data"]["nodes"]
        self.assertEqual(len(nodes), 2)
        for n in nodes:
            self.assertEqual(n["version"], 1)

    def test_self_loop_prevention_with_multiple_overlaps(self) -> None:
        """Multiple values appearing in both inputs and outputs all get bumped."""
        with comment_graph() as graph:
            with comment_session(session_name="s") as _:
                comment_variable("x", id_strategy="content")
                comment_variable("y", id_strategy="content")
                comment_op(
                    inputs=["x", "y"],
                    outputs=["x", "y"],
                    op_name="swap",
                    id_strategy="content",
                )

        exported = graph.export_graph()
        nodes = exported["data"]["nodes"]
        edges = exported["data"]["edges"]

        self.assertEqual(len(nodes), 4, "Expected v1+v2 for both x and y")
        for edge in edges:
            self.assertNotEqual(
                edge["source_full_node_id"],
                edge["target_full_node_id"],
            )
