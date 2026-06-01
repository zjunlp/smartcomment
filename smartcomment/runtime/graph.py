"""Read-only subgraph view with query and display methods."""

from ..analysis.visualization import _VISUAL_BACKENDS
from .operation import RuntimeEdge, RuntimeOp
from .variable import RuntimeVariable
from typing import (
    Any, 
    Self, 
    Iterable,
) 


class RuntimeGraph:
    """Read-only view over a subgraph."""

    __slots__ = (
        "nodes", "edges", "ops", 
        "_node_ids", "_op_ids", "_edge_ids"
    )

    def __init__(
        self,
        nodes: list[RuntimeVariable[Any]],
        edges: list[RuntimeEdge],
        ops: list[RuntimeOp],
    ) -> None:
        """Initialize the runtime graph handle.

        Args:
            nodes (`list[RuntimeVariable]`):
                The list of nodes in the subgraph.
            edges (`list[RuntimeEdge]`):
                The list of edges in the subgraph.
            ops (`list[RuntimeOp]`):
                The list of operations in the subgraph.
        """
        self.nodes = nodes
        self.edges = edges
        self.ops = ops
        self._node_ids = frozenset(n.full_node_id for n in nodes)
        self._op_ids = frozenset(o.op_id for o in ops)
        self._edge_ids = frozenset(e.edge_id for e in edges)

    def __contains__(self, full_node_id: str) -> bool:
        """Check whether a node with the given full node identifier exists.

        Args:
            full_node_id (`str`):
                The full node identifier to check.

        Returns:
            `bool`:
                ``True`` if the node exists in the subgraph, ``False``
                otherwise.
        """
        return full_node_id in self._node_ids

    def filter_by_category(self, category: str | Iterable[str]) -> Self:
        """Return a sub-view containing only nodes of the given category or categories.

        Args:
            category (`str | Iterable[str]`):
                A single category string or an iterable of category strings.

        Returns:
            `Self`:
                Filtered subgraph.
        """
        cats = {category} if isinstance(category, str) else set(category)
        matched = [n for n in self.nodes if n.category in cats]
        matched_ids = {n.full_node_id for n in matched}
        kept_edges = [
            e for e in self.edges
            if e.source_full_node_id in matched_ids and e.target_full_node_id in matched_ids
        ]
        kept_op_ids = {e.op_id for e in kept_edges}
        kept_ops = [o for o in self.ops if o.op_id in kept_op_ids]
        return type(self)(nodes=matched, edges=kept_edges, ops=kept_ops)

    def filter_by_time(
        self,
        start: str | None = None,
        end: str | None = None,
    ) -> Self:
        """Return a sub-view of nodes within a time range (inclusive).

        Args:
            start (`str | None`, optional):
                Inclusive lower bound timestamp.  If not provided, 
                it means no lower bound.
            end (`str | None`, optional):
                Inclusive upper bound timestamp.  If not provided, 
                it means no upper bound.

        Returns:
            `Self`:
                Filtered subgraph.
        """
        matched = [
            n for n in self.nodes
            if (start is None or n.created_at >= start)
            and (end is None or n.created_at <= end)
        ]
        matched_ids = {n.full_node_id for n in matched}
        kept_edges = [
            e for e in self.edges
            if e.source_full_node_id in matched_ids and e.target_full_node_id in matched_ids
        ]
        kept_op_ids = {e.op_id for e in kept_edges}
        kept_ops = [o for o in self.ops if o.op_id in kept_op_ids]
        return type(self)(nodes=matched, edges=kept_edges, ops=kept_ops)

    def time_range(self) -> tuple[str, str] | None:
        """Return the earliest and latest creation time among all runtime variables.

        Returns:
            `tuple[str, str] | None`:
                The earliest and latest creation time of variables in the 
                runtime graph if the runtime graph is not empty.
        """
        if not self.nodes:
            return None
        times = [n.created_at for n in self.nodes]
        return (min(times), max(times))

    def get_root_nodes(self) -> list[RuntimeVariable[Any]]:
        """Return nodes with zero in-degree (no incoming edges).

        Returns:
            `list[RuntimeVariable]`:
                Root nodes.
        """
        targets = {e.target_full_node_id for e in self.edges}
        return [n for n in self.nodes if n.full_node_id not in targets]

    def get_leaf_nodes(self) -> list[RuntimeVariable[Any]]:
        """Return nodes with zero out-degree (no outgoing edges).

        Returns:
            `list[RuntimeVariable]`:
                Leaf nodes.
        """
        sources = {e.source_full_node_id for e in self.edges}
        return [n for n in self.nodes if n.full_node_id not in sources]

    def induced_subgraph(self, full_node_ids: Iterable[str]) -> Self:
        """Return the induced subgraph over the given node identifiers.

        Nodes not present in this graph are silently skipped.

        Args:
            full_node_ids (`Iterable[str]`):
                The full node identifiers to include.

        Returns:
            `Self`:
                A sub-view containing only the specified nodes and the
                edges whose both endpoints are in the set.
        """
        id_set = set(full_node_ids)
        matched = [n for n in self.nodes if n.full_node_id in id_set]
        matched_ids = {n.full_node_id for n in matched}
        kept_edges = [
            e for e in self.edges
            if e.source_full_node_id in matched_ids
            and e.target_full_node_id in matched_ids
        ]
        kept_op_ids = {e.op_id for e in kept_edges}
        kept_ops = [o for o in self.ops if o.op_id in kept_op_ids]
        return type(self)(nodes=matched, edges=kept_edges, ops=kept_ops)

    def __and__(self, other: Self) -> Self:
        """Return the intersection of two graphs.

        Args:
            other (`Self`):
                The other graph.

        Returns:
            `Self`:
                The intersection graph.
        """
        if not isinstance(other, RuntimeGraph):
            return NotImplemented

        common_node_ids = self._node_ids & other._node_ids
        common_edge_ids = self._edge_ids & other._edge_ids

        nodes = [n for n in self.nodes if n.full_node_id in common_node_ids]
        edges = [
            e for e in self.edges
            if e.edge_id in common_edge_ids
            and e.source_full_node_id in common_node_ids
            and e.target_full_node_id in common_node_ids
        ]
        kept_op_ids = {e.op_id for e in edges}
        ops = [o for o in self.ops if o.op_id in kept_op_ids]

        return type(self)(nodes=nodes, edges=edges, ops=ops)

    def __or__(self, other: Self) -> Self:
        """Return the union of two graphs.

        Args:
            other (`Self`):
                The other graph.

        Returns:
            `Self`:
                The union graph.
        """
        if not isinstance(other, RuntimeGraph):
            return NotImplemented

        node_map= {
            n.full_node_id: n for n in self.nodes
        }
        for n in other.nodes:
            node_map.setdefault(n.full_node_id, n)

        op_map = {o.op_id: o for o in self.ops}
        for o in other.ops:
            op_map.setdefault(o.op_id, o)

        edge_map = {e.edge_id: e for e in self.edges}
        for e in other.edges:
            edge_map.setdefault(e.edge_id, e)

        return type(self)(
            nodes=list(node_map.values()),
            edges=list(edge_map.values()),
            ops=list(op_map.values()),
        )

    def __sub__(self, other: Self) -> Self:
        """Return the difference.

        Args:
            other (`Self`):
                The other graph.

        Returns:
            `Self`:
                The difference graph.
        """
        if not isinstance(other, RuntimeGraph):
            return NotImplemented

        diff_node_ids = self._node_ids - other._node_ids
        diff_op_ids = self._op_ids - other._op_ids

        nodes = [n for n in self.nodes if n.full_node_id in diff_node_ids]
        edges = [
            e for e in self.edges
            if e.op_id in diff_op_ids
            and e.source_full_node_id in diff_node_ids
            and e.target_full_node_id in diff_node_ids
        ]
        kept_op_ids = {e.op_id for e in edges}
        ops = [o for o in self.ops if o.op_id in kept_op_ids]

        return type(self)(nodes=nodes, edges=edges, ops=ops)

    def __xor__(self, other: Self) -> Self:
        """Return the symmetric difference of two graphs.

        Args:
            other (`Self`):
                The other graph.

        Returns:
            `Self`:
                The symmetric-difference graph.
        """
        if not isinstance(other, RuntimeGraph):
            return NotImplemented

        xor_node_ids = self._node_ids ^ other._node_ids
        xor_op_ids = self._op_ids ^ other._op_ids
        xor_edge_ids = self._edge_ids ^ other._edge_ids

        node_map = {}
        for n in (*self.nodes, *other.nodes):
            if n.full_node_id in xor_node_ids:
                node_map.setdefault(n.full_node_id, n)

        edges = [
            e for e in (*self.edges, *other.edges)
            if e.edge_id in xor_edge_ids
            and e.op_id in xor_op_ids
            and e.source_full_node_id in xor_node_ids
            and e.target_full_node_id in xor_node_ids
        ]

        kept_op_ids = {e.op_id for e in edges}
        op_map = {}
        for o in (*self.ops, *other.ops):
            if o.op_id in kept_op_ids:
                op_map.setdefault(o.op_id, o)

        return type(self)(
            nodes=list(node_map.values()),
            edges=edges,
            ops=list(op_map.values()),
        )

    def __eq__(self, other: object) -> bool:
        """Check structural equality by node, operation, and edge identifiers."""
        if not isinstance(other, RuntimeGraph):
            return NotImplemented
        return (
            self._node_ids == other._node_ids
            and self._op_ids == other._op_ids
            and self._edge_ids == other._edge_ids
        )

    def issubset(self, other: Self) -> bool:
        """Check whether every node, op, and edge in this graph also
        exists in another graph.

        Args:
            other (`Self`):
                The candidate supergraph.

        Returns:
            `bool`:
                ``True`` if this graph is a subgraph of another graph.
        """
        return (
            self._node_ids <= other._node_ids
            and self._op_ids <= other._op_ids
            and self._edge_ids <= other._edge_ids
        )

    def issuperset(self, other: Self) -> bool:
        """Check whether every node, operation, and edge in another graph also
        exists in this graph.

        Args:
            other (`Self`):
                The candidate subgraph.

        Returns:
            `bool`:
                ``True`` if this graph is a supergraph of another graph.
        """
        return (
            self._node_ids >= other._node_ids
            and self._op_ids >= other._op_ids
            and self._edge_ids >= other._edge_ids
        )

    def __le__(self, other: Self) -> bool:
        if not isinstance(other, RuntimeGraph):
            return NotImplemented
        return self.issubset(other)

    def __ge__(self, other: Self) -> bool:
        if not isinstance(other, RuntimeGraph):
            return NotImplemented
        return self.issuperset(other)

    def __lt__(self, other: Self) -> bool:
        if not isinstance(other, RuntimeGraph):
            return NotImplemented
        return self != other and self.issubset(other)

    def __gt__(self, other: Self) -> bool:
        if not isinstance(other, RuntimeGraph):
            return NotImplemented
        return self != other and self.issuperset(other)

    @property
    def edge_count(self) -> int:
        """Return the number of edges in the graph."""
        return len(self.edges)

    @property
    def op_count(self) -> int:
        """Return the number of operations in the graph."""
        return len(self.ops)

    @property
    def is_empty(self) -> bool:
        """Check whether the graph contains no nodes."""
        return len(self.nodes) == 0

    def visualize(self, backend: str = "graphviz", **kwargs: Any) -> Any:
        """Render this subgraph using a visualization backend.

        Args:
            backend (`str`, defaults to `"graphviz"`):
                Visualization backend name.
            **kwargs (`Any`):
                Forwarded to the backend.

        Returns:
            `Any`:
                The return value of the visualization backend.
        """
        if backend not in _VISUAL_BACKENDS:
            raise ValueError(
                f"'{backend}' is not a supported visualization backend. "
                "Available visualization backends " 
                f"are {', '.join(list(_VISUAL_BACKENDS.keys()))}."
            )
        return _VISUAL_BACKENDS[backend](
            self.nodes, 
            self.edges, 
            **kwargs
        )

    def __len__(self) -> int:
        """Get the number of nodes in the graph."""
        return len(self.nodes)

    def __repr__(self) -> str:
        """Get the string representation of the graph."""
        return (
            f"{self.__class__.__name__}(nodes={len(self.nodes)}, "
            f"edges={len(self.edges)}, "
            f"ops={len(self.ops)})"
        )

    def to_xml(
        self,
        *,
        include_metadata: bool = False,
        include_variable_value: bool = True,
    ) -> str:
        """Serialize the subgraph to an XML-like string for large language
        model consumption.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string element.
            include_variable_value (`bool`, defaults to `True`):
                When it is enabled, include stored values for variable nodes.

        Returns:
            `str`:
                XML representation.
        """
        if not self.nodes:
            return "<graph />"

        parts = ["<graph>"]
        parts.append("  <nodes>")
        for n in self.nodes:
            for line in n.to_xml(
                include_metadata=include_metadata,
                include_variable_value=include_variable_value,
            ).splitlines():
                parts.append(f"    {line}")
        parts.append("  </nodes>")

        if self.edges:
            parts.append("  <edges>")
            for e in self.edges:
                for line in e.to_xml(include_metadata=include_metadata).splitlines():
                    parts.append(f"    {line}")
            parts.append("  </edges>")

        if self.ops:
            parts.append("  <operations>")
            for o in self.ops:
                for line in o.to_xml(include_metadata=include_metadata).splitlines():
                    parts.append(f"    {line}")
            parts.append("  </operations>")

        parts.append("</graph>")
        return "\n".join(parts)

    def to_markdown(
        self,
        *,
        include_metadata: bool = False,
        include_variable_value: bool = True,
    ) -> str:
        """Serialize the subgraph to Markdown for large language model consumption.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string.
            include_variable_value (`bool`, defaults to `True`):
                When it is enabled, include stored values for variable nodes.

        Returns:
            `str`:
                Markdown representation.
        """
        lines = ["## Graph"]

        if not self.nodes:
            lines.append("\n*Empty graph.*")
            return "\n".join(lines)

        lines.append(f"\n### Nodes ({len(self.nodes)})\n")
        for n in self.nodes:
            lines.append(
                n.to_markdown(
                    include_metadata=include_metadata,
                    include_variable_value=include_variable_value,
                )
            )
            lines.append("")

        if self.edges:
            lines.append(f"### Edges ({len(self.edges)})\n")
            for e in self.edges:
                lines.append(e.to_markdown(include_metadata=include_metadata))
                lines.append("")

        if self.ops:
            lines.append(f"### Operations ({len(self.ops)})\n")
            for o in self.ops:
                lines.append(o.to_markdown(include_metadata=include_metadata))
                lines.append("")

        return "\n".join(lines)
