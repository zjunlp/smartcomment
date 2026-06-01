"""Pyvis visualization backend."""

from __future__ import annotations
from ...runtime.operation import RuntimeEdge
from ...runtime.variable import RuntimeVariable
from ._utils import _get_color_map, _truncate
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyvis.network import Network
    from matplotlib.colors import Colormap


_DEFAULT_BARNES_HUT = {
    "gravity": -12000,
    "central_gravity": 0.12,
    "spring_length": 400,
    "spring_strength": 0.001,
    "damping": 0.08,
    "overlap": 1,
}


def render_interactive(
    nodes: list[RuntimeVariable[Any]],
    edges: list[RuntimeEdge],
    filename: str = "exec_graph.html",
    node_cmap: str | Colormap | None = None,
    edge_cmap: str | Colormap | None = None,
    max_str_len: int = 30,
    smooth_type: str = "continuous",
    barnes_hut_config: dict[str, float | int] | None = None,
    **kwargs: Any,
) -> Network:
    """Render an interactive HTML graph via `pyvis`.

    Args:
        nodes (`list[RuntimeVariable]`):
            Variable nodes to render.
        edges (`list[RuntimeEdge]`):
            Edges to render.
        filename (`str`, defaults to `"exec_graph.html"`):
            Output HTML file path.
        node_cmap (`str | Colormap | None`, optional):
            Matplotlib colormap (name or object) for coloring nodes by
            category.
        edge_cmap (`str | Colormap | None`, optional):
            Matplotlib colormap (name or object) for coloring edges by
            category.
        max_str_len (`int`, defaults to `30`):
            Maximum string length for node/edge labels before truncation.
        smooth_type (`str`, defaults to `"continuous"`):
            Edge smoothing algorithm.
        barnes_hut_config (`dict[str, float | int] | None`, optional):
            Override the default BarnesHut physics parameters.
        **kwargs (`Any`):
            Additional keyword arguments to be passed to ``pyvis.network.Network``.

    Returns:
        `Network`:
            A `pyvis.network.Network` object.
    """
    try:
        from pyvis.network import Network as PyvisNetwork
    except ImportError as e:
        raise ImportError(
            "`pyvis` Python package is required. "
            "Install it via `pip install pyvis`."
        ) from e

    net = PyvisNetwork(**kwargs)

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
        # Pyvis default blueish. 
        color_hex = node_colors.get(cat, "#97C2FC")

        node_id_str = _truncate(node.full_node_id, max_len=max_str_len)
        raw_val_str = _truncate(node.raw_value, max_len=max_str_len)
        cat_str = _truncate(cat, max_len=max_str_len)
        tp_str = _truncate(node.trigger_point, max_len=max_str_len)
        comment_str = (
            _truncate(node.comment, max_len=max_str_len) if node.comment else ""
        )

        separator = "-" * max(15, min(30, max_str_len))
        label = (
            f"{node_id_str}\n{separator}\n"
            f"{raw_val_str}\ncategory: {cat_str}\n"
            f"trigger point: {tp_str}"
        )
        if comment_str:
            label += f"\n{separator}\n{comment_str}"

        title = (
            f"ID: {node.full_node_id}\nRaw Value: {node.raw_value}\n"
            f"Category: {cat}\nTrigger Point: {node.trigger_point}"
        )
        if node.comment:
            title += f"\nComment: {node.comment}"

        # All fields are left aligned.
        net.add_node(
            node.full_node_id,
            label=label,
            title=title,
            shape="box",
            color=color_hex,
            font={"align": "left"},
        )

    for edge in edges:
        cat = edge.category
        color_hex = edge_colors.get(cat, "#848484")
        tp_str = _truncate(edge.trigger_point, max_len=max_str_len)

        label_str = _truncate(edge.category, max_str_len)
        if edge.comment:
            label_str = _truncate(edge.comment, max_str_len)
        label_str += f"\n({tp_str})"

        title_str = f"Category: {cat}\nTrigger Point: {edge.trigger_point}"
        if edge.comment:
            title_str = (
                f"Category: {cat}\nComment: {edge.comment}\n"
                f"Trigger Point: {edge.trigger_point}"
            )

        net.add_edge(
            edge.source_full_node_id,
            edge.target_full_node_id,
            label=label_str,
            title=title_str,
            color=color_hex,
        )

    net.set_edge_smooth(smooth_type)

    bh = {**_DEFAULT_BARNES_HUT, **(barnes_hut_config or {})}
    net.barnes_hut(**bh)
    net.save_graph(filename)

    return net