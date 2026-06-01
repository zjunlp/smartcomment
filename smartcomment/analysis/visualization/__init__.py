"""Visualization backends for execution graphs.

Standalone functions accept user-facing runtime types so callers
can pass graph data without unwrapping internals.

Optional dependencies: ``graphviz``, ``pyvis``, ``matplotlib``.
Install with ``pip install smartcomment[viz]``.
"""

from collections import OrderedDict
from ...runtime.operation import RuntimeEdge
from ...runtime.variable import RuntimeVariable
from .graphviz import render_static, to_dot
from .pyvis import render_interactive
from typing import Any, Protocol


class GraphVisualizationBackend(Protocol):
    """Graph visualization backend protocol."""

    def __call__(
        self,
        nodes: list[RuntimeVariable[Any]],
        edges: list[RuntimeEdge],
        **kwargs: Any,
    ) -> Any:
        ...


_VISUAL_BACKENDS: OrderedDict[str, GraphVisualizationBackend] = OrderedDict(
    (
        ("graphviz", render_static),
        ("dot", to_dot),
        ("pyvis", render_interactive),
    )
)


__all__ = [
    "render_interactive",
    "render_static",
    "to_dot",
]