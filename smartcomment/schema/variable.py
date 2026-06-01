"""Variable schema. It is a single versioned value node in the execution graph."""

from pydantic import (
    Field,
    computed_field,
    field_validator,
)
from .base import TraceableModel


class Variable(TraceableModel):
    """Represent one persisted value version in the execution graph.

    A Variable is the internal graph element. Users interact with it
    through the runtime variable.
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Logical identity name produced by the identity strategy.",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Version number starting from 1.",
    )
    value: str = Field(
        ...,
        description="Encoded string representation of the runtime value.",
    )
    comment: str | None = Field(
        default=None,
        description="Developer-authored description or annotation.",
    )
    category: str = Field(
        default="variable",
        min_length=1,
        description="Variable category for filtering and visualization.",
    )
    graph_id: str = Field(
        ...,
        description="Identifier of the owning execution graph.",
    )
    user_id: str | None = Field(
        default=None,
        description="User that owns the execution graph.",
    )
    class_name: str | None = Field(
        default=None,
        description="Optional namespace derived from the Python class of the value.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project that owns the execution graph.",
    )
    session_id: str = Field(
        ...,
        description="Identifier of the session this variable belongs to.",
    )

    @field_validator("name")
    @classmethod
    def _name_must_contain_alnum(cls, v: str) -> str:
        """Validate that the variable name contains at least one alphanumeric character.

        Names consisting entirely of whitespace, punctuation, or special
        symbols are rejected because they carry no meaningful identity.

        Args:
            v (`str`):
                The raw variable name to validate.

        Returns:
            `str`:
                The validated variable name.

        Raises:
            `ValueError`:
                If the name has no alphanumeric character.
        """
        if not any(c.isalnum() for c in v):
            raise ValueError(
                f"Variable name must contain at least one alphanumeric character, "
                f"but '{v}' is found."
            )
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def full_name(self) -> str:
        """Namespaced variable name: ``{class_name}:{name}``.

        It falls back to the bare variable name when the class name is not provided.

        Returns:
            `str`:
                The full variable name.
        """
        if self.class_name is not None:
            return f"{self.class_name}:{self.name}"
        return self.name

    @computed_field  # type: ignore[prop-decorator]
    @property
    def node_id(self) -> str:
        """Unique identifier within the graph: ``{name}@{version}``.

        Returns:
            `str`:
                The node identifier.
        """
        return f"{self.name}@{self.version}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def full_node_id(self) -> str:
        """Namespaced identifier: ``{class_name}:{name}@{version}``.

        It falls back to the node identifier when the class name is not provided.

        Returns:
            `str`:
                The full node identifier.
        """
        return f"{self.full_name}@{self.version}"
