"""Read-only view wrapper for a tracing session."""

import json
from pydantic import JsonValue
from ..schema.session import Session


class RuntimeSession:
    """Read-only handle wrapping an internal session schema object."""

    __slots__ = ("_session",)

    def __init__(self, session: Session) -> None:
        """Initialize the runtime session handle.

        Args:
            session (`Session`):
                The internal session schema to wrap.
        """
        self._session = session

    @property
    def session_id(self) -> str:
        """Get the session identifier."""
        return self._session.session_id

    @property
    def session_name(self) -> str | None:
        """Get the human-readable session name."""
        return self._session.session_name

    @property
    def graph_id(self) -> str:
        """Get the owning graph identifier."""
        return self._session.graph_id

    @property
    def user_id(self) -> str | None:
        """Get the user identifier."""
        return self._session.user_id

    @property
    def project_id(self) -> str | None:
        """Get the project identifier."""
        return self._session.project_id

    @property
    def comment(self) -> str | None:
        """Get the session description."""
        return self._session.comment

    @property
    def category(self) -> str:
        """Get the session category."""
        return self._session.category

    @property
    def metadata(self) -> dict[str, JsonValue]:
        """Get the session metadata."""
        return self._session.metadata

    @property
    def trigger_point(self) -> str:
        """Get the trigger point of this session."""
        return self._session.trigger_point

    @property
    def created_at(self) -> str:
        """Get the creation timestamp."""
        return self._session.created_at

    def __repr__(self) -> str:
        """Get the string representation of the session."""
        name = self._session.session_name or self._session.session_id
        return (
            f"{self.__class__.__name__}({name!r}, id={self._session.session_id!r}, "
            f"category={self._session.category!r}, comment={self._session.comment!r})"
        )

    def to_xml(self, *, include_metadata: bool = False) -> str:
        """Serialize to an XML-like string for large language model consumption.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string element.

        Returns:
            `str`:
                XML representation.
        """
        parts = [
            f'<session id="{self._session.session_id}"',
        ]
        if self._session.session_name:
            parts[0] += f' name="{self._session.session_name}"'
        parts[0] += f' category="{self._session.category}">'
        if self._session.comment:
            parts.append(f"  <comment>{self._session.comment}</comment>")
        parts.append(
            f"  <created_at>created in the system at {self._session.created_at}</created_at>"
        )
        if include_metadata and self.metadata:
            parts.append(
                f"  <metadata>{json.dumps(self.metadata, ensure_ascii=False)}</metadata>"
            )
        parts.append("</session>")
        return "\n".join(parts)

    def to_markdown(self, *, include_metadata: bool = False) -> str:
        """Serialize to a Markdown string for large language model consumption.

        Args:
            include_metadata (`bool`, defaults to `False`):
                When it is enabled, include metadata as a JSON string.

        Returns:
            `str`:
                Markdown representation.
        """
        name = self._session.session_name or self._session.session_id
        lines = [f"**Session: {name}**"]
        lines.append(f"- Session ID: `{self._session.session_id}`")
        lines.append(f"- Category: {self._session.category}")
        if self._session.comment:
            lines.append(f"- Comment: {self._session.comment}")
        lines.append(
            f"- Created At: created in the system at `{self._session.created_at}`"
        )
        if include_metadata and self.metadata:
            lines.append(
                f"- Metadata: `{json.dumps(self.metadata, ensure_ascii=False)}`"
            )
        return "\n".join(lines)
