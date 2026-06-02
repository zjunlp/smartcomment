"""Tracing context multi-alias tests."""

from __future__ import annotations

from smartcomment import (
    comment_graph,
    comment_session,
    comment_variable,
    current_context,
)
from tests.helpers import BaseTracingTest


class TracingContextMultiAliasTests(BaseTracingTest):
    """Regression tests for the ``full_node_id -> {name, ...}`` reverse index.

    The previous implementation stored only one name per full node identifier,
    so registering the same runtime variable under multiple names silently
    dropped all but the most recent alias from the reverse map and made
    ``get_variable_by_full_node_id`` and ``remove_variable`` unsafe in several
    configurations. These tests pin down the corrected behavior.
    """

    def test_register_same_rv_under_multiple_names(self) -> None:
        """Registering the same rv under two names keeps both aliases alive."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("a", rv)
                ctx.register_variable("b", rv)

                self.assertIs(ctx.get_variable("a"), rv)
                self.assertIs(ctx.get_variable("b"), rv)
                self.assertIs(
                    ctx.get_variable_by_full_node_id(rv.full_node_id), rv
                )
                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv.full_node_id),
                    {"a", "b"},
                )

    def test_remove_one_alias_preserves_other(self) -> None:
        """Removing one alias must not invalidate other aliases of the same rv."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("a", rv)
                ctx.register_variable("b", rv)

                ctx.remove_variable("a")

                # 'b' still resolves by name
                self.assertIs(ctx.get_variable("b"), rv)
                # Reverse index still finds the rv
                self.assertIs(
                    ctx.get_variable_by_full_node_id(rv.full_node_id), rv
                )
                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv.full_node_id), {"b"}
                )

    def test_remove_last_alias_drops_reverse_entry(self) -> None:
        """After removing the final alias, the reverse index drops the key."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("a", rv)
                ctx.register_variable("b", rv)
                ctx.remove_variable("a")
                ctx.remove_variable("b")

                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv.full_node_id), set()
                )
                with self.assertRaises(NameError):
                    ctx.get_variable_by_full_node_id(rv.full_node_id)
                with self.assertRaises(NameError):
                    ctx.remove_variable("b")  # already gone

    def test_remove_does_not_double_pop_when_aliased(self) -> None:
        """Removing two aliases in any order must not raise KeyError.

        The old implementation stored one reverse entry per full_node_id and
        popped it unconditionally on ``remove_variable``, so after the first
        removal the second one raised ``KeyError`` from the underlying dict.
        """
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("a", rv)
                ctx.register_variable("b", rv)

                ctx.remove_variable("b")
                ctx.remove_variable("a")

    def test_overwrite_same_name_with_different_rv(self) -> None:
        """Overwriting a name must detach it from the old rv's alias set."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv1 = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                rv2 = comment_variable(
                    "world",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("x", rv1)
                ctx.register_variable("x", rv2, overwrite=True)

                self.assertIs(ctx.get_variable("x"), rv2)
                # The stale reverse entry for rv1 must be gone.
                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv1.full_node_id), set()
                )
                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv2.full_node_id), {"x"}
                )
                # Looking up by rv1 identifier raises, not returns rv2.
                with self.assertRaises(NameError):
                    ctx.get_variable_by_full_node_id(rv1.full_node_id)
                self.assertIs(
                    ctx.get_variable_by_full_node_id(rv2.full_node_id), rv2
                )

    def test_overwrite_without_flag_raises(self) -> None:
        """``overwrite=False`` still blocks name collisions."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("x", rv)
                with self.assertRaises(ValueError):
                    ctx.register_variable("x", rv)

    def test_overwrite_with_same_rv_is_idempotent(self) -> None:
        """Re-registering the same name-rv pair must not lose the alias."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None

                ctx.register_variable("x", rv)
                ctx.register_variable("x", rv, overwrite=True)

                self.assertIs(ctx.get_variable("x"), rv)
                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv.full_node_id), {"x"}
                )

    def test_child_context_inherits_deep_copy_of_alias_sets(self) -> None:
        """Nested contexts must not share set objects with the parent.

        Before the fix, the reverse index was shallow-copied. With sets as
        values, mutations inside a nested ``comment_session`` /
        ``propagate_attributes`` scope leaked back into the parent context.
        """
        with comment_graph():
            with comment_session(session_name="outer"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    to_runtime=True,
                )
                outer_ctx = current_context()
                assert outer_ctx is not None
                outer_ctx.register_variable("a", rv)

                with comment_session(session_name="inner"):
                    inner_ctx = current_context()
                    assert inner_ctx is not None
                    # Register a second alias only in the child scope.
                    inner_ctx.register_variable("b", rv)
                    # Remove the inherited alias only in the child.
                    inner_ctx.remove_variable("a")

                    self.assertEqual(
                        inner_ctx.get_names_by_full_node_id(rv.full_node_id),
                        {"b"},
                    )

                # Parent alias set is untouched.
                self.assertEqual(
                    outer_ctx.get_names_by_full_node_id(rv.full_node_id),
                    {"a"},
                )

    def test_comment_variable_variable_name_with_rv_plus_extra_alias(self) -> None:
        """An explicit ``comment_variable`` path + an extra alias coexist."""
        with comment_graph():
            with comment_session(session_name="s"):
                rv = comment_variable(
                    "hello",
                    id_strategy="content",
                    variable_name="primary",
                    to_runtime=True,
                )
                ctx = current_context()
                assert ctx is not None
                ctx.register_variable("secondary", rv)

                self.assertIs(ctx.get_variable("primary"), rv)
                self.assertIs(ctx.get_variable("secondary"), rv)
                self.assertEqual(
                    ctx.get_names_by_full_node_id(rv.full_node_id),
                    {"primary", "secondary"},
                )
