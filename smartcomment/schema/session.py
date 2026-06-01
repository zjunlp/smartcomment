"""Session schema. It is a logical grouping of traced operations within a graph."""

from uuid import uuid4
from pydantic import Field
from .base import TraceableModel


class Session(TraceableModel):
    """Represent a tracing session inside an execution graph.

    Sessions partition the graph into logical phases while sharing the 
    same underlying graph storage.
    """

    session_id: str = Field(
        default_factory=lambda: f"session-{uuid4().hex}",
        description="Unique session identifier.",
    )
    session_name: str | None = Field(
        default=None,
        description="Human-readable session name.",
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
    comment: str | None = Field(
        default=None,
        description="Developer-authored session description.",
    )
    category: str = Field(
        default="session",
        description="Session category for filtering.",
    )
