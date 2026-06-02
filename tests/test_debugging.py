"""draw_graph debugging utility tests."""

from __future__ import annotations

from smartcomment import (
    comment_fn,
    comment_op,
)
from tests.helpers import BaseTracingTest


class DrawGraphTests(BaseTracingTest):
    """Tests for the draw_graph debugging utility."""

    def test_draw_graph_returns_dot_string(self) -> None:
        """draw_graph with backend='dot' returns a DOT string."""
        from smartcomment.debugging import draw_graph

        def pipeline(x: int, y: int) -> None:
            comment_op(
                inputs=[x],
                outputs=[y],
                op_name="transform",
                id_strategy="content",
            )

        result = draw_graph(
            pipeline,
            fn_kwargs={"x": 10, "y": 20},
            backend="dot",
        )
        self.assertIsInstance(result, str)
        self.assertIn("digraph", result)
        self.assertIn("exec_graph", result)

    def test_draw_graph_creates_anonymous_graph(self) -> None:
        """The execution graph created by draw_graph does not persist."""
        from smartcomment.debugging import draw_graph
        from smartcomment import current_graph

        def simple(a: str, b: str) -> None:
            comment_op(
                inputs=[a], outputs=[b],
                op_name="pipe", id_strategy="content",
            )

        draw_graph(simple, fn_kwargs={"a": "in", "b": "out"}, backend="dot")
        self.assertIsNone(current_graph())

    def test_draw_graph_with_async_fn(self) -> None:
        """draw_graph supports async entry functions."""
        from smartcomment.debugging import draw_graph

        async def async_pipeline(a: int, b: int) -> None:
            comment_op(
                inputs=[a],
                outputs=[b],
                op_name="async_op",
                id_strategy="content",
            )

        result = draw_graph(
            async_pipeline,
            fn_kwargs={"a": 1, "b": 2},
            backend="dot",
        )
        self.assertIsInstance(result, str)
        self.assertIn("digraph", result)

    def test_draw_graph_with_comment_fn(self) -> None:
        """draw_graph works with comment_fn decorated functions."""
        from smartcomment.debugging import draw_graph

        @comment_fn(op_name="double")
        def double(x: int) -> int:
            return x * 2

        def pipeline(val: int) -> None:
            double(val)

        result = draw_graph(pipeline, fn_kwargs={"val": 5}, backend="dot")
        self.assertIsInstance(result, str)
        self.assertIn("digraph", result)
