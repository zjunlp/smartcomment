"""Graphviz visualization backend."""

from __future__ import annotations
from ...runtime.operation import RuntimeEdge
from ...runtime.variable import RuntimeVariable
from ._utils import (
    _get_color_map, 
    _escape_html, 
    _truncate,
)
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from matplotlib.colors import Colormap
    from graphviz import Source


def to_dot(
    nodes: list[RuntimeVariable[Any]],
    edges: list[RuntimeEdge],
    node_cmap: str | Colormap | None = None,
    edge_cmap: str | Colormap | None = None,
    max_str_len: int = 30,
    **kwargs: Any,
) -> str:
    """Convert a node list and an edge list to a `graphviz` DOT string.

    Args:
        nodes (`list[RuntimeVariable]`):
            Variable nodes to render.
        edges (`list[RuntimeEdge]`):
            Edges to render.
        node_cmap (`str | Colormap | None`, optional):
            Matplotlib colormap (name or object) for coloring nodes by category.
        edge_cmap (`str | Colormap | None`, optional):
            Matplotlib colormap (name or object) for coloring edges by category.
        max_str_len (`int`, defaults to `30`):
            Maximum string length for displayed fields before truncation.
        **kwargs (`Any`):
            These keyword arguments will be ignored.

    Returns:
        `str`:
            DOT-format string.
    """
    lines = [
        'digraph exec_graph {', 
        '  rankdir=LR;',
        '  node [shape=none, fontname="Helvetica"];',
        '  edge [fontname="Helvetica"];'
    ]

    # Get unique categories for nodes and edges.
    node_cats = {n.category for n in nodes}
    edge_cats = {e.category for e in edges}


    if node_cats:
        node_colors = _get_color_map(node_cats, cmap=node_cmap)
    else:
        node_colors = {}
    if edge_cats:
        edge_colors = _get_color_map(edge_cats, cmap=edge_cmap)
    else:
        edge_colors = {}

    for node in nodes:
        cat = node.category
        # Default white background. 
        color_hex = node_colors.get(cat, "#FFFFFF")  
        
        node_id_str = _escape_html(
            _truncate(
                node.full_node_id, 
                max_len=max_str_len
            )
        )
        raw_val_str = _escape_html(
            _truncate(
                node.raw_value, 
                max_len=max_str_len
            )
        )
        cat_str = _escape_html(
            _truncate(
                node.category, 
                max_len=max_str_len
            )
        )
        tp_str = _escape_html(
            _truncate(
                node.trigger_point, 
                max_len=max_str_len
            )
        )
        comment_str = _escape_html(
            _truncate(node.comment, max_len=max_str_len) if node.comment else ""
        )

        # Pad empty comments with a space to prevent the cell from collapsing. 
        comment_display = comment_str if comment_str else " "

        # Build HTML-like record with strict BALIGN="LEFT" and <BR ALIGN="LEFT"/>. 
        label = (
            f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4" BGCOLOR="{color_hex}">\n'
            f'  <TR><TD ALIGN="CENTER"><B>{node_id_str}</B></TD></TR>\n'
            f'  <TR><TD ALIGN="LEFT" BALIGN="LEFT">'
            f'{raw_val_str}<BR ALIGN="LEFT"/>'
            f'category: {cat_str}<BR ALIGN="LEFT"/>'
            f'trigger point: {tp_str}<BR ALIGN="LEFT"/>'
            f'</TD></TR>\n'
            f'  <TR><TD ALIGN="LEFT" BALIGN="LEFT">{comment_display}<BR ALIGN="LEFT"/></TD></TR>\n'
            f'</TABLE>>'
        )
        
        lines.append(f'  "{node.full_node_id}" [label={label}];')

    for edge in edges:
        cat = edge.category
        # Default black for edges. 
        color_hex = edge_colors.get(cat, "#000000")  
        
        label = _escape_html(
            _truncate(
                edge.category, 
                max_len=max_str_len
            )
        )
        if edge.comment:
            label = _escape_html(
                _truncate(
                    edge.comment, 
                    max_len=max_str_len
                )
            )
            
        lines.append(
            f'  "{edge.source_full_node_id}" -> "{edge.target_full_node_id}" '
            f'[label="{label}", color="{color_hex}", fontcolor="{color_hex}"];'
        )

    lines.append("}")
    return "\n".join(lines)


def render_static(
    nodes: list[RuntimeVariable[Any]],
    edges: list[RuntimeEdge],
    filename: str = "exec_graph",
    format: str = "png",
    node_cmap: str | Colormap | None = None,
    edge_cmap: str | Colormap | None = None,
    max_str_len: int = 30,
    **kwargs: Any,
) -> Source:
    """Render a graph to a static image file via `graphviz`.

    Args:
        nodes (`list[RuntimeVariable]`):
            Variable nodes to render.
        edges (`list[RuntimeEdge]`):
            Edges to render.
        filename (`str`, defaults to `"exec_graph"`):
            Output filename (without extension).
        format (`str`, defaults to `"png"`):
            Image format (``"png"``, ``"svg"``, ``"pdf"``).
        node_cmap (`str | Colormap | None`, optional):
            Matplotlib colormap (name or object) for coloring nodes by category.
        edge_cmap (`str | Colormap | None`, optional):
            Matplotlib colormap (name or object) for coloring edges by category.
        max_str_len (`int`, defaults to `30`):
            Maximum characters for text display.
        **kwargs (`Any`):
            Additional keyword arguments to be passed to ``graphviz.Source.render``.

    Returns:
        `Source`:
            A `graphviz.Source` object.
    """
    try:
        import graphviz as gv
    except ImportError as e:
        raise ImportError(
            "`graphviz` Python package is required. "
            "Install it via `pip install graphviz`."
        ) from e

    dot_str = to_dot(
        nodes=nodes,
        edges=edges,
        node_cmap=node_cmap,
        edge_cmap=edge_cmap,
        max_str_len=max_str_len,
    )
    src = gv.Source(dot_str, format=format)
    kwargs.setdefault("cleanup", True)
    kwargs.setdefault("view", False)
    src.render(filename=filename, **kwargs)

    return src 
