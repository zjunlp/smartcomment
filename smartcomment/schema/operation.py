"""Operation schema."""

from uuid import uuid4
from pydantic import Field
from .base import TraceableModel


class OpRecord(TraceableModel):
    """Represent a traced operation over existing nodes.

    An operation record captures the what and why of an operation. The
    structural relationships (which nodes are connected) live on
    operation edge instances that reference this record.
    """

    op_id: str = Field(
        default_factory=lambda: f"op-{uuid4().hex}",
        description="Unique operation identifier.",
    )
    op_name: str | None = Field(
        default=None,
        description="Canonical operation name.",
    )
    comment: str | None = Field(
        default=None,
        description="Developer-authored high-level description.",
    )
    category: str = Field(
        default="operation",
        description="Operation category for grouping and visualization.",
    )
    graph_id: str = Field(
        ...,
        description="Identifier of the owning execution graph.",
    )
    user_id: str | None = Field(
        default=None,
        description="User that owns the execution graph.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project that owns the execution graph.",
    )
    session_id: str = Field(
        ...,
        description="Identifier of the session this operation belongs to.",
    )


class OpEdge(TraceableModel):
    """Represent a directed edge between two variable nodes.

    Each edge is emitted by exactly one operation record and connects
    a source (upstream) node to a target (downstream) node.
    """

    edge_id: str = Field(
        default_factory=lambda: f"edge-{uuid4().hex}",
        description="Unique edge identifier.",
    )
    graph_id: str = Field(
        ...,
        description="Identifier of the owning execution graph.",
    )
    user_id: str | None = Field(
        default=None,
        description="User that owns the execution graph.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project that owns the execution graph.",
    )
    session_id: str = Field(
        ...,
        description="Identifier of the session this edge belongs to.",
    )
    op_id: str = Field(
        ...,
        description="Identifier of the operation that produced this edge.",
    )
    category: str = Field(
        default="operation",
        description="Edge category (typically mirrors the operation category).",
    )
    source_full_node_id: str = Field(
        ...,
        description="Full node identifier of the upstream variable.",
    )
    target_full_node_id: str = Field(
        ...,
        description="Full node identifier of the downstream variable.",
    )
    comment: str | None = Field(
        default=None,
        description="Optional annotation for this edge.",
    )
