"""Read-only view wrappers for graph elements."""

import json
from pydantic import JsonValue
from ..schema.operation import OpEdge, OpRecord


class RuntimeOp:
    """Read-only view wrapping an operation record."""

    __slots__ = ("_op",)

    def __init__(self, op: OpRecord) -> None:
        """Initialize the runtime operation handle.

        Args:
            op (`OpRecord`):
                The internal operation record to wrap.
        """
        self._op = op

    @property
    def op_id(self) -> str:
        """Get the operation identifier."""
        return self._op.op_id

    @property
    def op_name(self) -> str | None:
        """Get the operation name."""
        return self._op.op_name

    @property
    def comment(self) -> str | None:
        """Get the operation comment."""
        return self._op.comment

    @property
    def category(self) -> str:
        """Get the operation category."""
        return self._op.category

    @property
    def metadata(self) -> dict[str, JsonValue]:
        """Get the operation metadata."""
        return self._op.metadata

    @property
    def graph_id(self) -> str:
        """Get the owning graph identifier."""
        return self._op.graph_id

    @property
    def session_id(self) -> str:
        """Get the owning session identifier."""
        return self._op.session_id

    @property
    def user_id(self) -> str | None:
        """Get the user identifier."""
        return self._op.user_id

    @property
    def project_id(self) -> str | None:
        """Get the project identifier."""
        return self._op.project_id

    @property
    def trigger_point(self) -> str:
        """Get the trigger point of this operation."""
        return self._op.trigger_point

    @property
    def created_at(self) -> str:
        """Get the creation timestamp."""
        return self._op.created_at

    def __repr__(self) -> str:
        """Get the string representation of the operation."""
        return (
            f"RuntimeOp({self._op.op_name!r}, id={self._op.op_id!r}, " 
            f"category={self._op.category!r}, comment={self._op.comment!r})"
        )

    def to_xml(self, *, include_metadata: bool = False) -> str:
        """Serialize to an XML-like string.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string element.

        Returns:
            `str`:
                XML representation.
        """
        parts = [f'<operation id="{self._op.op_id}" name="{self._op.op_name}" category="{self._op.category}">']
        if self._op.comment:
            parts.append(f"  <comment>{self._op.comment}</comment>")
        parts.append(
            f"  <created_at>created in the system at {self._op.created_at}</created_at>"
        )
        if include_metadata and self.metadata:
            parts.append(
                f"  <metadata>{json.dumps(self.metadata, ensure_ascii=False)}</metadata>"
            )
        parts.append("</operation>")
        return "\n".join(parts)

    def to_markdown(self, *, include_metadata: bool = False) -> str:
        """Serialize to a Markdown string.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string.

        Returns:
            `str`:
                Markdown representation.
        """
        name = self._op.op_name or "UNNAMED"
        lines = [f"**Op: {name}**"]
        lines.append(f"- Operation ID: `{self._op.op_id}`")
        lines.append(f"- Category: {self._op.category}")
        if self._op.comment:
            lines.append(f"- Comment: {self._op.comment}")
        lines.append(
            f"- Created At: created in the system at `{self._op.created_at}`"
        )
        if include_metadata and self.metadata:
            lines.append(
                f"- Metadata: `{json.dumps(self.metadata, ensure_ascii=False)}`"
            )
        return "\n".join(lines)


class RuntimeEdge:
    """Read-only view wrapping an operation edge."""

    __slots__ = ("_edge",)

    def __init__(self, edge: OpEdge) -> None:
        """Initialize the runtime edge handle.

        Args:
            edge (`OpEdge`):
                The internal edge record to wrap.
        """
        self._edge = edge

    @property
    def edge_id(self) -> str:
        """Get the edge identifier."""
        return self._edge.edge_id

    @property
    def source_full_node_id(self) -> str:
        """Get the source full node identifier."""
        return self._edge.source_full_node_id

    @property
    def target_full_node_id(self) -> str:
        """Get the target full node identifier."""
        return self._edge.target_full_node_id

    @property
    def op_id(self) -> str:
        """Get the operation identifier."""
        return self._edge.op_id

    @property
    def comment(self) -> str | None:
        """Get the edge comment."""
        return self._edge.comment

    @property
    def category(self) -> str:
        """Get the edge category."""
        return self._edge.category

    @property
    def graph_id(self) -> str:
        """Get the owning graph identifier."""
        return self._edge.graph_id

    @property
    def session_id(self) -> str:
        """Get the owning session identifier."""
        return self._edge.session_id

    @property
    def user_id(self) -> str | None:
        """Get the user identifier."""
        return self._edge.user_id

    @property
    def project_id(self) -> str | None:
        """Get the project identifier."""
        return self._edge.project_id

    @property
    def metadata(self) -> dict[str, JsonValue]:
        """Get the edge metadata."""
        return self._edge.metadata

    @property
    def trigger_point(self) -> str:
        """Get the trigger point of this edge."""
        return self._edge.trigger_point

    @property
    def created_at(self) -> str:
        """Get the creation timestamp."""
        return self._edge.created_at

    def __repr__(self) -> str:
        """Get the string representation of the edge."""
        return (
            f"{self.__class__.__name__}({self._edge.source_full_node_id!r} -> {self._edge.target_full_node_id!r}, "
            f"op_id={self._edge.op_id!r}, category={self._edge.category!r}, "
            f"comment={self._edge.comment!r})"
        )

    def to_xml(self, *, include_metadata: bool = False) -> str:
        """Serialize to an XML-like string.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string element.

        Returns:
            `str`:
                XML representation.
        """
        parts = [
            f'<edge id="{self._edge.edge_id}" '
            f'source="{self._edge.source_full_node_id}" '
            f'target="{self._edge.target_full_node_id}" '
            f'category="{self._edge.category}">'
        ]
        if self._edge.comment:
            parts.append(f"  <comment>{self._edge.comment}</comment>")
        parts.append(
            f"  <created_at>created in the system at {self._edge.created_at}</created_at>"
        )
        if include_metadata and self.metadata:
            parts.append(
                f"  <metadata>{json.dumps(self.metadata, ensure_ascii=False)}</metadata>"
            )
        parts.append("</edge>")
        return "\n".join(parts)

    def to_markdown(self, *, include_metadata: bool = False) -> str:
        """Serialize to a Markdown string.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string.

        Returns:
            `str`:
                Markdown representation.
        """
        lines = [f"**Edge: `{self._edge.source_full_node_id}` -> `{self._edge.target_full_node_id}`**"]
        lines.append(f"- Edge ID: `{self._edge.edge_id}`")
        lines.append(f"- Category: {self._edge.category}")
        if self._edge.comment:
            lines.append(f"- Comment: {self._edge.comment}")
        lines.append(
            f"- Created At: created in the system at `{self._edge.created_at}`"
        )
        if include_metadata and self.metadata:
            lines.append(
                f"- Metadata: `{json.dumps(self.metadata, ensure_ascii=False)}`"
            )
        return "\n".join(lines)
