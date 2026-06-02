"""comment_fn decorator tests."""

from __future__ import annotations

from smartcomment import (
    comment_fn,
    comment_graph,
    comment_link,
    comment_op_scope,
    comment_variable,
    disable_tracing,
)
from tests.helpers import BaseTracingTest


class CommentFnEnhancedTests(BaseTracingTest):
    """Tests for the enhanced comment_fn decorator (async, param_options)."""

    def test_comment_fn_sync_basic(self) -> None:
        """comment_fn wraps a sync function and records op + edges."""
        @comment_fn(op_name="add")
        def add(a: int, b: int) -> int:
            return a + b

        with comment_graph() as graph:
            result = add(2, 3)

        self.assertEqual(result, 5)
        self.assertEqual(graph.op_count, 1)
        self.assertGreater(graph.edge_count, 0)

    def test_comment_fn_async_basic(self) -> None:
        """comment_fn wraps an async function and records op + edges."""
        import asyncio

        @comment_fn(op_name="async_add")
        async def async_add(a: int, b: int) -> int:
            return a + b

        with comment_graph() as graph:
            result = asyncio.run(async_add(10, 20))

        self.assertEqual(result, 30)
        self.assertEqual(graph.op_count, 1)
        self.assertGreater(graph.edge_count, 0)

    def test_comment_fn_async_preserves_coroutine_nature(self) -> None:
        """The wrapper of an async function is itself a coroutine function."""
        import asyncio

        @comment_fn(op_name="coro_check")
        async def coro(x: int) -> int:
            return x * 2

        self.assertTrue(asyncio.iscoroutinefunction(coro))

    def test_comment_fn_param_options(self) -> None:
        """param_options supplies per-parameter overrides."""
        @comment_fn(
            op_name="greet",
            param_options={
                "name": {"id_strategy": "content", "category": "param_input"},
            },
        )
        def greet(name: str, greeting: str = "hi") -> str:
            return f"{greeting} {name}"

        with comment_graph() as graph:
            result = greet("Alice", "hello")

        self.assertEqual(result, "hello Alice")
        self.assertEqual(graph.op_count, 1)
        nodes = graph.get_all_nodes()
        categories = {n.category for n in nodes}
        self.assertIn("param_input", categories)
        param_nodes = [n for n in nodes if n.category == "param_input"]
        self.assertEqual(len(param_nodes), 1)
        self.assertEqual(param_nodes[0].raw_value, "'Alice'")

    def test_comment_fn_shared_encoding_fn(self) -> None:
        """Shared encoding_fn applies to all auto-created variables."""
        @comment_fn(
            op_name="upper",
            encoding_fn=lambda v: str(v).upper(),
        )
        def upper(text: str) -> str:
            return text.upper()

        with comment_graph() as graph:
            upper("hello")

        nodes = graph.get_all_nodes()
        for n in nodes:
            self.assertEqual(n.raw_value, n.raw_value.upper())

    def test_comment_fn_shared_id_strategy(self) -> None:
        """Shared id_strategy is used for all parameters without overrides."""
        @comment_fn(
            op_name="concat",
            id_strategy="content",
        )
        def concat(a: str, b: str) -> str:
            return a + b

        with comment_graph() as graph:
            concat("foo", "bar")

        self.assertEqual(graph.op_count, 1)
        nodes = graph.get_all_nodes()
        self.assertEqual(len(nodes), 3)
        values = {n.raw_value for n in nodes}
        self.assertIn("'foo'", values)
        self.assertIn("'bar'", values)
        self.assertIn("'foobar'", values)

    def test_comment_fn_noop_when_disabled(self) -> None:
        """comment_fn is a no-op when tracing is disabled."""
        @comment_fn(op_name="noop")
        def noop(x: int) -> int:
            return x + 1

        disable_tracing()
        with comment_graph() as graph:
            result = noop(5)

        self.assertIsNone(graph)
        self.assertEqual(result, 6)

    def test_comment_fn_none_return(self) -> None:
        """Functions returning None produce no output variable."""
        @comment_fn(op_name="void_fn")
        def void_fn(x: int) -> None:
            pass

        with comment_graph() as graph:
            void_fn(42)

        self.assertEqual(graph.op_count, 1)

    def test_comment_fn_docstring_as_comment(self) -> None:
        """When no comment is provided, the docstring is used."""
        @comment_fn(op_name="documented")
        def documented(x: int) -> int:
            """Double the input value."""
            return x * 2

        with comment_graph() as graph:
            documented(5)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertIn("documented", ops[0].comment)
        self.assertIn("Double the input value.", ops[0].comment)

    def test_comment_fn_no_docstring_uses_qualname(self) -> None:
        """When no comment and no docstring, qualname is the fallback."""
        @comment_fn(op_name="bare")
        def bare(x: int) -> int:
            return x

        with comment_graph() as graph:
            bare(1)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertIn("bare", ops[0].comment)
        self.assertNotIn("[", ops[0].comment)

    def test_comment_fn_explicit_comment_overrides_docstring(self) -> None:
        """An explicit comment takes precedence over the docstring."""
        @comment_fn(op_name="explicit", comment="My custom description")
        def with_doc(x: int) -> int:
            """This docstring should be ignored."""
            return x

        with comment_graph() as graph:
            with_doc(1)

        ops = graph.get_all_operations()
        self.assertEqual(ops[0].comment, "My custom description")

    def test_comment_fn_op_metadata_on_op_not_variables(self) -> None:
        """op_metadata is attached to the operation, not to variables."""
        @comment_fn(
            op_name="tagged",
            op_metadata={"source": "unit_test"},
        )
        def tagged(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            tagged(10)

        ops = graph.get_all_operations()
        self.assertEqual(ops[0].metadata["source"], "unit_test")
        for node in graph.get_all_nodes():
            self.assertNotIn("source", node.metadata)

    def test_comment_fn_variable_metadata_on_variables_not_op(self) -> None:
        """metadata is attached to auto-created variables, not to the op."""
        @comment_fn(
            op_name="var_tagged",
            metadata={"origin": "test"},
        )
        def var_tagged(x: int) -> int:
            return x * 2

        with comment_graph() as graph:
            var_tagged(3)

        ops = graph.get_all_operations()
        self.assertNotIn("origin", ops[0].metadata)
        for node in graph.get_all_nodes():
            self.assertEqual(node.metadata["origin"], "test")

    def test_comment_fn_both_metadata_separated(self) -> None:
        """op_metadata and metadata are independent."""
        @comment_fn(
            op_name="dual",
            op_metadata={"op_key": "op_val"},
            metadata={"var_key": "var_val"},
        )
        def dual(x: int) -> int:
            return x

        with comment_graph() as graph:
            dual(1)

        ops = graph.get_all_operations()
        self.assertIn("op_key", ops[0].metadata)
        self.assertNotIn("var_key", ops[0].metadata)

        for node in graph.get_all_nodes():
            self.assertIn("var_key", node.metadata)
            self.assertNotIn("op_key", node.metadata)



class CommentFnV2Tests(BaseTracingTest):
    """Tests for enhanced comment_fn: optional op_name, op reuse, include_source."""

    def test_op_name_defaults_to_qualname(self) -> None:
        """When op_name is omitted, fn.__qualname__ is used."""
        @comment_fn()
        def my_func(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            my_func(5)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertIn("my_func", ops[0].op_name)

    def test_explicit_op_name_still_works(self) -> None:
        """Explicit op_name takes precedence over qualname."""
        @comment_fn(op_name="custom_name")
        def my_func(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            my_func(5)

        ops = graph.get_all_operations()
        self.assertEqual(ops[0].op_name, "custom_name")

    def test_reuses_active_op_scope(self) -> None:
        """When inside comment_op_scope, edges use the outer op."""
        @comment_fn()
        def add(a: int, b: int) -> int:
            return a + b

        with comment_graph() as graph:
            with comment_op_scope(op_name="outer_pipeline") as outer_op:
                add(2, 3)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "outer_pipeline")

        edges = graph.get_all_edges()
        for edge in edges:
            self.assertEqual(edge.op_id, outer_op.op_id)

    def test_creates_own_op_when_no_scope(self) -> None:
        """Without comment_op_scope, comment_fn creates its own operation."""
        @comment_fn()
        def double(x: int) -> int:
            return x * 2

        with comment_graph() as graph:
            double(4)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertIn("double", ops[0].op_name)

    def test_sets_op_context_for_inner_comment_link(self) -> None:
        """Inner comment_link calls see the op created by comment_fn."""
        @comment_fn()
        def pipeline(a: int) -> int:
            rv = comment_variable(a * 10, to_runtime=True, id_strategy="content")
            comment_link(source=a, target=rv, category="inner")
            return a * 10

        with comment_graph() as graph:
            pipeline(3)

        edges = graph.get_all_edges()
        inner_edges = [e for e in edges if e.category == "inner"]
        self.assertEqual(len(inner_edges), 1)
        fn_ops = [op for op in graph.get_all_operations()
                  if "pipeline" in (op.op_name or "")]
        self.assertEqual(len(fn_ops), 1)
        self.assertEqual(inner_edges[0].op_id, fn_ops[0].op_id)

    def test_include_source_not_on_op_metadata(self) -> None:
        """include_source=True does not leak source into the op record metadata.

        By design, ``comment_fn(include_source=True)`` attaches the captured
        function source only to edge metadata. The operation record is meant
        to describe the operation identity, not to carry the (potentially
        large) source payload on every op.
        """
        @comment_fn(include_source=True)
        def traced(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            traced(5)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertNotIn("source_code", ops[0].metadata)

    def test_include_source_on_edge_metadata(self) -> None:
        """include_source=True puts source code in edge metadata."""
        @comment_fn(include_source=True)
        def traced(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            traced(5)

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertIn("source_code", edge.metadata)
            self.assertIn("def traced", edge.metadata["source_code"])

    def test_include_source_false_by_default(self) -> None:
        """By default, source code is not included."""
        @comment_fn()
        def plain(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            plain(5)

        ops = graph.get_all_operations()
        self.assertNotIn("source_code", ops[0].metadata)

    def test_include_source_with_reused_op_goes_to_edges_only(self) -> None:
        """When reusing an outer op, source code appears on edges but not op."""
        @comment_fn(include_source=True)
        def inner(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            with comment_op_scope(op_name="outer") as outer_op:
                inner(5)

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertNotIn("source_code", ops[0].metadata)

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertIn("source_code", edge.metadata)

    def test_async_with_op_reuse(self) -> None:
        """Async comment_fn reuses active op scope."""
        import asyncio

        @comment_fn()
        async def async_add(a: int, b: int) -> int:
            return a + b

        with comment_graph() as graph:
            with comment_op_scope(op_name="async_outer") as outer_op:
                asyncio.run(async_add(1, 2))

        ops = graph.get_all_operations()
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].op_name, "async_outer")

    def test_category_and_comment_on_edges_when_reused(self) -> None:
        """Category and comment from comment_fn are applied to edges."""
        @comment_fn(category="fn_cat", comment="fn_comment")
        def tagged(x: int) -> int:
            return x + 1

        with comment_graph() as graph:
            with comment_op_scope(op_name="outer", category="outer_cat"):
                tagged(5)

        edges = graph.get_all_edges()
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertEqual(edge.category, "fn_cat")
            self.assertEqual(edge.comment, "fn_comment")

    def test_op_context_reset_on_exception(self) -> None:
        """_OP context is properly reset even if the function raises."""
        from smartcomment.runtime.context import _OP

        @comment_fn()
        def fail(x: int) -> int:
            raise ValueError("boom")

        with comment_graph() as graph:
            before = _OP.get()
            with self.assertRaises(ValueError):
                fail(1)
            after = _OP.get()
            self.assertEqual(before, after)
