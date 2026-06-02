"""Strict-mode and identity_only tests."""

from __future__ import annotations

from smartcomment import (
    comment_fn,
    comment_graph,
    comment_link,
    comment_mutation,
    comment_op,
    comment_op_scope,
    comment_session,
    comment_variable,
)
from smartcomment.runtime.network import ExecNetwork
from smartcomment.runtime.variable import RuntimeVariable
from smartcomment.runtime.errors import TraceConsistencyError
from tests.helpers import (
    BaseTracingTest,
    MemoryItem,
)


class StrictModeTests(BaseTracingTest):
    """Test strict consistency checking in smartcomment."""

    # ------------------------------------------------------------------
    # Strict is a graph attribute
    # ------------------------------------------------------------------

    def test_strict_default_is_false(self) -> None:
        """Graphs default to non-strict mode."""
        with comment_graph() as graph:
            self.assertFalse(graph.strict)

    def test_strict_set_via_comment_graph(self) -> None:
        """comment_graph(strict=True) creates a strict graph."""
        with comment_graph(strict=True) as graph:
            self.assertTrue(graph.strict)

    def test_strict_persists_on_existing_graph(self) -> None:
        """Passing an existing graph preserves its strict setting unless
        explicitly overridden."""
        g = ExecNetwork(strict=True)
        with comment_graph(graph=g) as graph:
            self.assertTrue(graph.strict)

        with comment_graph(graph=g, strict=False) as graph:
            self.assertFalse(graph.strict)

    def test_strict_visible_across_sessions(self) -> None:
        """Session scopes see the graph's strict flag."""
        with comment_graph(strict=True) as graph:
            with comment_session(session_name="s1"):
                self.assertTrue(graph.strict)

    # ------------------------------------------------------------------
    # Strict mode raises on untraced mutation via comment_variable
    # ------------------------------------------------------------------

    def test_strict_raises_on_changed_value_via_comment_variable(self) -> None:
        """comment_variable raises TraceConsistencyError in strict mode
        when a tracked value changes without comment_mutation."""
        item = MemoryItem(memory_id="mem-strict-1", content="before")

        with comment_graph(strict=True):
            with comment_session(session_name="strict-test"):
                comment_variable(item, comment="Initial registration.")

                item.content = "after"
                with self.assertRaises(TraceConsistencyError) as cm:
                    comment_variable(item, comment="Should fail in strict mode.")

                err = cm.exception
                self.assertIn("mem-strict-1", str(err))
                self.assertIn("Untraced mutation detected", str(err))
                self.assertEqual(err.identity_name, "mem-strict-1")
                self.assertIs(err.user_value, item)
                self.assertIsInstance(err.existing_variable, RuntimeVariable)

    def test_strict_raises_on_changed_value_via_comment_op_input(self) -> None:
        """comment_op raises TraceConsistencyError when an input value
        has changed in strict mode."""
        item = MemoryItem(memory_id="mem-strict-2", content="original")

        with comment_graph(strict=True):
            with comment_session(session_name="strict-test"):
                comment_variable(item, comment="Track item.")

                item.content = "mutated-silently"
                with self.assertRaises(TraceConsistencyError):
                    comment_op(
                        inputs=[item],
                        outputs=[("result", {"id_strategy": "content"})],
                        op_name="use_item",
                    )

    def test_strict_raises_on_changed_value_via_comment_op_output(self) -> None:
        """comment_op raises TraceConsistencyError when an output value
        has changed in strict mode."""
        item = MemoryItem(memory_id="mem-strict-3", content="v1")

        with comment_graph(strict=True):
            with comment_session(session_name="strict-test"):
                comment_variable(item, comment="Track item.")

                item.content = "v2"
                with self.assertRaises(TraceConsistencyError):
                    comment_op(
                        inputs=[("some_input", {"id_strategy": "content"})],
                        outputs=[item],
                        op_name="produce_item",
                    )

    # ------------------------------------------------------------------
    # Non-strict mode: same situation should NOT raise
    # ------------------------------------------------------------------

    def test_non_strict_auto_versions_on_changed_value(self) -> None:
        """In non-strict mode, a changed value auto-creates a new version."""
        item = MemoryItem(memory_id="mem-lenient-1", content="before")

        with comment_graph(strict=False) as graph:
            with comment_session(session_name="lenient-test"):
                rv1 = comment_variable(item, comment="Initial.", to_runtime=True)
                self.assertEqual(rv1.version, 1)

                item.content = "after"
                rv2 = comment_variable(item, comment="Auto-versioned.", to_runtime=True)
                self.assertEqual(rv2.version, 2)
                self.assertEqual(rv2.name, rv1.name)

    # ------------------------------------------------------------------
    # Strict mode + comment_mutation: the correct way
    # ------------------------------------------------------------------

    def test_strict_allows_comment_mutation(self) -> None:
        """comment_mutation works fine in strict mode -- it is the
        intended way to record value changes."""
        item = MemoryItem(memory_id="mem-strict-ok", content="before")

        with comment_graph(strict=True) as graph:
            with comment_session(session_name="strict-mutation"):
                comment_variable(item, comment="Initial.")
                with comment_mutation(
                    target=item,
                    mutation_comment="Proper mutation.",
                ) as scope:
                    item.content = "after"
                new_rv = scope.result

                self.assertIsNotNone(new_rv)
                self.assertEqual(new_rv.version, 2)
                versions = graph.get_versions(new_rv.full_name)
                self.assertEqual(len(versions), 2)

    # ------------------------------------------------------------------
    # Error message quality
    # ------------------------------------------------------------------

    def test_error_message_includes_diagnostic_info(self) -> None:
        """The error message should contain the identity, node_id,
        version, diff context around the change, and actionable suggestions."""
        item = MemoryItem(memory_id="mem-diag", content="original")

        with comment_graph(strict=True):
            with comment_session(session_name="diag-test"):
                rv = comment_variable(item, comment="Track it.")

                item.content = "changed"
                try:
                    comment_variable(item, comment="Boom.")
                    self.fail("Expected TraceConsistencyError")
                except TraceConsistencyError as exc:
                    msg = str(exc)
                    self.assertIn("mem-diag", msg)
                    self.assertIn("mem-diag@1", msg)
                    self.assertIn("v1", msg)
                    self.assertIn("original", msg)
                    self.assertIn("changed", msg)
                    self.assertIn("comment_mutation", msg)
                    self.assertIn("strict", msg)
                    self.assertIn("Recorded", msg)
                    self.assertIn("Provided", msg)

    def test_diff_context_shows_surrounding_chars(self) -> None:
        """_diff_context returns snippets centred on the first differing character."""
        from smartcomment.runtime.errors import _diff_context

        old = "the quick brown fox jumps over the lazy dog"
        new = "the quick brown cat jumps over the lazy dog"
        old_snip, new_snip = _diff_context(old, new, max_chars=30)

        self.assertIn("fox", old_snip)
        self.assertIn("cat", new_snip)
        self.assertIn("brown", old_snip)
        self.assertIn("brown", new_snip)

    def test_diff_context_ellipsis_for_long_strings(self) -> None:
        """_diff_context adds ellipsis when the window does not cover the
        full string."""
        from smartcomment.runtime.errors import _diff_context

        prefix = "A" * 200
        old = prefix + "ORIGINAL" + "B" * 200
        new = prefix + "MODIFIED" + "B" * 200

        old_snip, new_snip = _diff_context(old, new, max_chars=40)

        self.assertTrue(old_snip.startswith("..."))
        self.assertTrue(old_snip.endswith("..."))
        self.assertIn("ORIGINAL", old_snip)
        self.assertTrue(new_snip.startswith("..."))
        self.assertTrue(new_snip.endswith("..."))
        self.assertIn("MODIFIED", new_snip)

    def test_diff_context_identical_prefix_different_length(self) -> None:
        """When one string is a prefix of the other, diff starts at the
        end of the shorter one."""
        from smartcomment.runtime.errors import _diff_context

        old = "alpha beta"
        new = "alpha beta gamma delta"
        old_snip, new_snip = _diff_context(old, new, max_chars=40)

        self.assertIn("alpha", old_snip)
        self.assertIn("gamma", new_snip)

    def test_diff_context_short_strings_no_ellipsis(self) -> None:
        """Short strings that fit within max_chars should have no ellipsis."""
        from smartcomment.runtime.errors import _diff_context

        old = "abc"
        new = "axc"
        old_snip, new_snip = _diff_context(old, new, max_chars=120)

        self.assertEqual(old_snip, "abc")
        self.assertEqual(new_snip, "axc")

    # ------------------------------------------------------------------
    # Same value re-registration should NOT raise in strict mode
    # ------------------------------------------------------------------

    def test_strict_allows_same_value_re_registration(self) -> None:
        """Re-registering the exact same value should not raise, even
        in strict mode (no inconsistency)."""
        item = MemoryItem(memory_id="mem-same", content="stable")

        with comment_graph(strict=True):
            with comment_session(session_name="same-value"):
                rv1 = comment_variable(item, comment="First time.", to_runtime=True)
                rv2 = comment_variable(item, comment="Second time, same value.", to_runtime=True)

                self.assertEqual(rv1.full_node_id, rv2.full_node_id)
                self.assertEqual(rv1.version, rv2.version)

    # ------------------------------------------------------------------
    # Strict mode with comment_fn decorator
    # ------------------------------------------------------------------

    def test_strict_raises_through_comment_fn(self) -> None:
        """comment_fn auto-tracing respects strict mode."""
        item = MemoryItem(memory_id="mem-fn-strict", content="initial")

        @comment_fn(op_name="test.identity")
        def identity(x: MemoryItem) -> MemoryItem:
            return x

        with comment_graph(strict=True):
            with comment_session(session_name="fn-strict"):
                identity(item)

                item.content = "mutated"
                with self.assertRaises(TraceConsistencyError):
                    identity(item)

    # ------------------------------------------------------------------
    # Cross-session strict mode
    # ------------------------------------------------------------------

    def test_strict_across_sessions(self) -> None:
        """Strict checking works across multiple sessions within the
        same graph."""
        item = MemoryItem(memory_id="mem-cross", content="session1-val")

        with comment_graph(strict=True):
            with comment_session(session_name="s1"):
                comment_variable(item, comment="Created in session 1.")

            item.content = "session2-val"
            with comment_session(session_name="s2"):
                with self.assertRaises(TraceConsistencyError):
                    comment_variable(item, comment="Changed in session 2.")

    # ------------------------------------------------------------------
    # Strict persists through export/import
    # ------------------------------------------------------------------

    def test_strict_survives_export_import(self) -> None:
        """The strict flag persists through export_graph / import_graph."""
        with comment_graph(strict=True) as graph:
            with comment_session(session_name="persist"):
                comment_variable("hello", id_strategy="content")
            exported = graph.export_graph()

        imported = ExecNetwork.import_graph(exported)
        self.assertTrue(imported.strict)

    # ------------------------------------------------------------------
    # identity_only: per-variable opt-out of snapshot consistency check
    # ------------------------------------------------------------------

    def test_identity_only_bypasses_strict_error(self) -> None:
        """identity_only=True on comment_variable skips the strict check
        and returns the existing node when the snapshot differs."""
        item = MemoryItem(memory_id="id-only-1", content="full snapshot")

        with comment_graph(strict=True) as graph:
            with comment_session(session_name="identity-only-test"):
                rv1 = comment_variable(item, comment="Full.", to_runtime=True)

                item.content = "lightweight ref"
                rv2 = comment_variable(
                    item, comment="Ref.", to_runtime=True, identity_only=True,
                )

                self.assertEqual(rv1.full_node_id, rv2.full_node_id)
                self.assertEqual(rv2.version, 1)
                self.assertEqual(rv2.raw_value, rv1.raw_value)

    def test_identity_only_returns_existing_in_non_strict(self) -> None:
        """identity_only=True in non-strict mode returns the existing node
        without creating a new version."""
        item = MemoryItem(memory_id="id-only-2", content="original")

        with comment_graph(strict=False) as graph:
            with comment_session(session_name="identity-only-ns"):
                rv1 = comment_variable(item, comment="v1.", to_runtime=True)

                item.content = "changed"
                rv2 = comment_variable(
                    item, comment="No new version.", to_runtime=True,
                    identity_only=True,
                )

                self.assertEqual(rv1.full_node_id, rv2.full_node_id)
                self.assertEqual(rv2.version, 1)

    def test_identity_only_creates_node_when_none_exists(self) -> None:
        """identity_only=True still creates a new node when there is no
        existing node for the identity (first registration)."""
        item = MemoryItem(memory_id="id-only-new", content="first time")

        with comment_graph(strict=True):
            with comment_session(session_name="identity-only-new"):
                rv = comment_variable(
                    item, comment="Brand new.", to_runtime=True,
                    identity_only=True,
                )
                self.assertEqual(rv.version, 1)
                self.assertEqual(rv.name, "id-only-new")

    def test_identity_only_via_comment_op_options(self) -> None:
        """identity_only can be passed via the per-item options dict
        in comment_op inputs/outputs."""
        item = MemoryItem(memory_id="id-only-op", content="full")

        with comment_graph(strict=True) as graph:
            with comment_session(session_name="identity-only-op"):
                rv1 = comment_variable(item, comment="Track.", to_runtime=True)

                item.content = "slim ref"
                op = comment_op(
                    inputs=[(item, {"identity_only": True})],
                    outputs=[("result", {"id_strategy": "content"})],
                    op_name="use_item_lightly",
                )
                self.assertIsNotNone(op)

    def test_identity_only_via_comment_link_options(self) -> None:
        """identity_only can be passed via per-item options in comment_link."""
        item = MemoryItem(memory_id="id-only-link", content="full")

        with comment_graph(strict=True):
            with comment_session(session_name="id-only-link"):
                rv1 = comment_variable(item, to_runtime=True)

                item.content = "partial"
                with comment_op_scope(op_name="link-test"):
                    edge = comment_link(
                        source=(item, {"identity_only": True}),
                        target=("downstream", {"id_strategy": "content"}),
                    )
                    self.assertIsNotNone(edge)

    def test_identity_only_false_still_raises_in_strict(self) -> None:
        """Explicitly passing identity_only=False (default) still raises
        TraceConsistencyError in strict mode."""
        item = MemoryItem(memory_id="id-only-false", content="before")

        with comment_graph(strict=True):
            with comment_session(session_name="id-only-false"):
                comment_variable(item, comment="Track.")

                item.content = "after"
                with self.assertRaises(TraceConsistencyError):
                    comment_variable(item, identity_only=False)
