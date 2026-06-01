"""Runtime error types for smartcomment tracing."""

from .variable import RuntimeVariable
from typing import Any


def _diff_context(old: str, new: str, max_chars: int = 120) -> tuple[str, str]:
    """Return context snippets around the first character where 
    old value and new value diverge.

    It locates the first differing character index, then extracts a
    window of at most `max_chars` characters centred on that position
    from each string.  Ellipsis markers are prepended and appended when 
    the window does not cover the full string.

    Args:
        old (`str`):
            The previously recorded encoded value.
        new (`str`):
            The newly provided encoded value.
        max_chars (`int`, defaults to `120`):
            Maximum number of characters to show in each snippet.

    Returns:
        `tuple[str, str]`:
            A tuple of two strings with context around the
            first difference.
    """
    diff_idx = 0
    for i, (oc, nc) in enumerate(zip(old, new)):
        if oc != nc:
            diff_idx = i
            break
    else:
        diff_idx = min(len(old), len(new))

    half = max_chars // 2
    start = max(0, diff_idx - half)

    def _snippet(s: str) -> str:
        end = min(len(s), start + max_chars)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(s) else ""
        return f"{prefix}{s[start:end]}{suffix}"

    return _snippet(old), _snippet(new)


class TraceConsistencyError(RuntimeError):
    """It is raised in strict mode when a tracked value diverges from 
    its recorded state.

    This typically means a value was mutated in-place without going
    through `comment_mutation`. The error message includes both the 
    user-provided value and the existing variable node so that the 
    developer can quickly identify the inconsistency.
    """

    def __init__(
        self,
        *,
        user_value: Any,
        user_value_encoded: str,
        existing_variable: RuntimeVariable[Any],
        identity_name: str,
    ) -> None:
        """Initialize the error.

        Args:
            user_value (`Any`):
                The raw Python value that the caller tried to register.
            user_value_encoded (`str`):
                The encoded string of the user-provided value.
            existing_variable (`RuntimeVariable[Any]`):
                The existing variable node stored in the graph.
            identity_name (`str`):
                The identity name that both values resolve to.
        """
        self.user_value = user_value
        self.user_value_encoded = user_value_encoded
        self.existing_variable = existing_variable
        self.identity_name = identity_name

        message = self._build_message()
        super().__init__(message)

    def _build_message(self) -> str:
        """Build a human-readable diagnostic message."""
        ev = self.existing_variable
        old_snippet, new_snippet = _diff_context(ev.raw_value, self.user_value_encoded)

        lines = [
            "Untraced mutation detected in strict mode.",
            "",
            f"  Variable name (identity)      : {self.identity_name!r}",
            f"  Existing full node identifier : {ev.full_node_id}",
            f"  Existing version number       : v{ev.version}",
            "",
            "  Diff (first changed character with context):",
            f"    Recorded : {old_snippet}",
            f"    Provided : {new_snippet}",
            "",
            "The value bound to this identity has changed since it was last "
            "recorded, but no `comment_mutation` call was made. In strict "
            "mode this is treated as an error.",
            "",
            "To fix this, either:",
            "  1. Use `comment_mutation(target=rv, new_value=...)` to record "
            "the change explicitly.",
            "  2. Disable strict mode: `comment_graph(strict=False)` or "
            "`graph.strict = False`.",
        ]
        return "\n".join(lines)


class ExecNetworkKeyError(KeyError):
    """It is raised when a key error occurs in the execution network."""
