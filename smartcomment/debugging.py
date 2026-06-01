"""Debugging utilities for execution graph visualization.

This module provides one-shot trace-and-visualize helpers that create
an anonymous (non-persistent) execution graph, run user code inside it,
and render the resulting graph.  It is intended for interactive debugging and
quick inspection of traced pipelines.
"""

import asyncio
from .runtime.context import comment_graph
from typing import Any, Callable


def draw_graph(
    fn: Callable,
    /,
    *,
    fn_kwargs: dict[str, Any] | None = None,
    backend: str = "graphviz",
    **kwargs: Any,
) -> Any:
    """Trace a function call and visualize the resulting execution graph.

    It creates an anonymous execution graph, runs the given function 
    inside it so that all ``comment_*`` calls within function are captured, 
    then renders the graph using the specified visualization backend.  
    The graph is discarded after visualization. This function is purely for
    debugging and does not persist any data.

    Both synchronous and asynchronous entry functions are supported.     
    However, if the function you pass in opens its own ``comment_graph`` block, 
    anything that runs inside that inner block is written to a different graph object.  
    When the inner block ends, the context switches back, but ``draw_graph`` 
    still only knows about the outer graph it opens first.  As a result, 
    the picture you get may miss most of the nodes and edges, or look nearly empty, 
    even though tracing does occur.

    Example::

        from smartcomment import draw_graph

        def my_pipeline(query: str, k: int) -> None:
            ...  # calls comment_op, comment_variable, etc.

        draw_graph(my_pipeline, fn_kwargs={"query": "hello", "k": 5})

    Args:
        fn (`Callable`):
            Entry-point function whose body contains ``comment_*`` calls.
        fn_kwargs (`dict[str, Any] | None`, optional):
            Keyword arguments forwarded to the given function.
        backend (`str`, defaults to `"graphviz"`):
            Visualization backend name.
        **kwargs (`Any`):
            Additional keyword arguments forwarded to the visualization
            backend.

    Returns:
        `Any`:
            The return value of the visualization backend.
    """
    with comment_graph() as graph:
        if asyncio.iscoroutinefunction(fn):
            asyncio.run(fn(**(fn_kwargs or {})))
        else:
            fn(**(fn_kwargs or {}))

    return graph.visualize(backend=backend, **kwargs)

