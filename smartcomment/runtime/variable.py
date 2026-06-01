"""The user-facing handle wrapping an internal variable node."""

import json
from pydantic import BaseModel, JsonValue
from ..schema.variable import Variable
from typing import (
    Callable,
    Generic,
    TypeVar,
    cast,
)


T = TypeVar("T")


class RuntimeVariable(Generic[T]):
    """Read-only handle that wraps a variable node in the execution graph."""

    __slots__ = (
        "_variable",
        "encoding_fn",
        "decoding_fn",
        "schema",
    )

    def __init__(
        self,
        variable: Variable,
        *,
        encoding_fn: Callable[[T], str] | None = None,
        decoding_fn: Callable[[str], T] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> None:
        """Initialize the runtime variable handle.

        Args:
            variable (`Variable`):
                The internal graph variable to wrap.
            encoding_fn (`Callable[[T], str] | None`, optional):
                If provided, it encodes a Python variable value to the string representation.
            decoding_fn (`Callable[[str], T] | None`, optional):
                If provided, it decodes the string representation back to a Python variable value.
            schema (`type[BaseModel] | None`, optional):
                If provided, any missing encoding or decoding function is filled
                from the schema via the pydantic methods `model_dump_json` and `model_validate_json`.
        """
        self._variable = variable

        if schema is not None:
            enc = encoding_fn
            dec = decoding_fn
            if enc is None:
                enc = cast(
                    Callable[[T], str] | None,
                    lambda v: v.model_dump_json()
                )
            if dec is None:
                dec = cast(
                    Callable[[str], T] | None,
                    lambda s: schema.model_validate_json(s),
                )
            self.encoding_fn = enc
            self.decoding_fn = dec
            self.schema = schema
        else:
            self.encoding_fn = encoding_fn
            self.decoding_fn = decoding_fn
            self.schema = None

    @property
    def name(self) -> str:
        """Get the logical variable name."""
        return self._variable.name

    @property
    def full_name(self) -> str:
        """Get the namespaced variable name."""
        return self._variable.full_name

    @property
    def version(self) -> int:
        """Get the current version number."""
        return self._variable.version

    @property
    def node_id(self) -> str:
        """Get the graph node identifier."""
        return self._variable.node_id

    @property
    def full_node_id(self) -> str:
        """Get the namespaced node identifier."""
        return self._variable.full_node_id

    @property
    def raw_value(self) -> str:
        """Get the encoded string stored in the graph."""
        return self._variable.value

    @property
    def value(self) -> T | str:
        """Get the decoded Python variable value, or the raw string if no decoder is set."""
        if self.decoding_fn is not None:
            return self.decoding_fn(self._variable.value)
        return self._variable.value

    @property
    def comment(self) -> str | None:
        """Get the developer-authored annotation."""
        return self._variable.comment

    @property
    def category(self) -> str:
        """Get the variable category."""
        return self._variable.category

    @property
    def class_name(self) -> str | None:
        """Get the class-name namespace."""
        return self._variable.class_name

    @property
    def graph_id(self) -> str:
        """Get the owning graph identifier."""
        return self._variable.graph_id

    @property
    def session_id(self) -> str:
        """Get the owning session identifier."""
        return self._variable.session_id

    @property
    def user_id(self) -> str | None:
        """Get the user identifier."""
        return self._variable.user_id

    @property
    def project_id(self) -> str | None:
        """Get the project identifier."""
        return self._variable.project_id

    @property
    def trigger_point(self) -> str:
        """Get the trigger point of this variable."""
        return self._variable.trigger_point

    @property
    def created_at(self) -> str:
        """Get the creation timestamp."""
        return self._variable.created_at

    @property
    def metadata(self) -> dict[str, JsonValue]:
        """Get the variable metadata."""
        return self._variable.metadata

    def __repr__(self) -> str:
        """Get the string representation of the variable value."""
        return f"{self._variable.value!r}"

    def to_xml(
        self,
        *,
        include_metadata: bool = False,
        include_variable_value: bool = True,
    ) -> str:
        """Serialize to an XML-like string for large language model consumption.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string element.
            include_variable_value (`bool`, defaults to `True`):
                When it is enabled, include the stored variable value.

        Returns:
            `str`:
                XML representation.
        """
        parts = [
            f'<variable full_node_id="{self.full_node_id}" name="{self.name}" version="{self.version}"',
        ]
        if self.class_name:
            parts[0] += f' class="{self.class_name}"'
        parts[0] += f' category="{self.category}">'
        if include_variable_value:
            parts.append(f"  <value>{self._variable.value}</value>")
        if self.comment:
            parts.append(f"  <comment>{self.comment}</comment>")
        parts.append(
            f"  <created_at>created in the system at {self.created_at}</created_at>"
        )
        if include_metadata and self.metadata:
            parts.append(
                f"  <metadata>{json.dumps(self.metadata, ensure_ascii=False)}</metadata>"
            )
        parts.append("</variable>")
        return "\n".join(parts)

    def to_markdown(
        self,
        *,
        include_metadata: bool = False,
        include_variable_value: bool = True,
    ) -> str:
        """Serialize to a Markdown string for large language model consumption.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string.
            include_variable_value (`bool`, defaults to `True`):
                When it is enabled, include the stored variable value.

        Returns:
            `str`:
                Markdown representation.
        """
        header = f"**{self._variable.name}** (v{self.version})"
        if self.class_name:
            header += f" [{self.class_name}]"
        lines = [
            header,
            f"- Full Node ID: `{self.full_node_id}`",
        ]
        if include_variable_value:
            lines.append(f"- Value: `{self._variable.value}`")
        if self.comment:
            lines.append(f"- Comment: {self.comment}")
        lines.append(f"- Category: {self.category}")
        lines.append(
            f"- Created At: created in the system at `{self.created_at}`"
        )
        if include_metadata and self.metadata:
            lines.append(
                f"- Metadata: `{json.dumps(self.metadata, ensure_ascii=False)}`"
            )
        return "\n".join(lines)
