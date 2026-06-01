"""Internal helpers for the public API."""

import contextlib
import inspect
from pydantic import BaseModel, JsonValue
from ..runtime import (
    ExecNetwork,
    none_session_id,
    current_graph,
    current_session,
    current_context,
    none_identity,
)
from ..runtime.variable import RuntimeVariable
from ..runtime.errors import TraceConsistencyError, _diff_context
from ..schema.variable import Variable
from ..identity.registry import IdentityRegistry
from ..logging import logger
from typing import (
    Any, 
    Callable, 
    TypeVar, 
)


T = TypeVar("T")


def _resolve_identity(
    value: Any,
    *,
    id_strategy: Callable[[Any], str] | str | None = None,
) -> str:
    """Resolve the identity string for a value.

    Args:
        value (`Any`):
            The value to resolve the identity for.
        id_strategy (`Callable[[Any], str] | str | None`, optional):
            The identity strategy to use. If not provided, it will be looked up by type.

    Returns:
        `str`:
            The resolved identity string.

    Raises:
        `ValueError`:
            If the identity is the built-in NONE sentinel.
    """
    fn = IdentityRegistry.resolve(value, override=id_strategy)
    identity = fn(value)

    none_id = none_identity()
    if identity == none_id:
        raise ValueError(
            f"The identity '{none_id}' is reserved for the built-in "
            "NONE sentinel. Choose a different identity strategy."
        )
    return identity


def _resolve_call_context(
    caller_name: str = "comment_*",
    stack_level: int = 2,
) -> tuple[ExecNetwork, str, str, int]:
    """Resolve the active graph, session identifier, and caller location.

    It obtains the current execution graph, determines the current session 
    identifier (falling back to the NONE sentinel session when no session is active),
    and captures the caller's source location for attribution.

    Args:
        caller_name (`str`, defaults to `"comment_*"`):
            Name of the calling public function, included in the error
            message when no graph context is active.
        stack_level (`int`, defaults to `2`):
            Frame index passed to ``inspect.stack`` to locate the
            original call site.

    Returns:
        `tuple[ExecNetwork, str, str, int]`:
            A 4-tuple including the current execution graph, session identifier,
            caller's source location and line number.

    Raises:
        `RuntimeError`:
            If no graph context is active.
    """
    graph = current_graph()
    if graph is None:
        raise RuntimeError(
            f"`{caller_name}` requires an active graph context. "
            "Wrap your code in `with comment_graph() as graph:`."
        )

    session = current_session()
    if session is not None:
        session_id = session.session_id
    else:
        # Check whether the NONE sentinel session has been inserted yet. 
        graph._ensure_none_session()
        session_id = none_session_id()

    frame = inspect.stack()[stack_level]
    filename, lineno = frame.filename, frame.lineno
    return graph, session_id, filename, lineno


def _ensure_variable(
    value: T,
    *,
    graph: ExecNetwork,
    session_id: str,
    filename: str,
    lineno: int,
    id_strategy: Callable[[T], str] | str | None = None,
    encoding_fn: Callable[[T], str] | None = None,
    decoding_fn: Callable[[str], T] | None = None,
    schema: type[BaseModel] | None = None,
    comment: str | None = None,
    category: str = "variable",
    class_name: str | None = None,
    auto_class_name: bool = False,
    variable_name: str | None = None,
    metadata: dict[str, JsonValue] | None = None,
    identity_only: bool = False,
    force_new_version: bool = False,
) -> RuntimeVariable[T]:
    """Create or reuse a graph variable node and return a runtime handle.

    It resolves the variable to a stable identity, encodes it to a string for storage,
    and either reuses the latest matching node (same encoded value) or
    appends a new version.  When the variable's name is set and a tracing context
    exists, the handle is registered for lookup by name.

    Args:
        value (`T`):
            The Python value to record in the graph.
        graph (`ExecNetwork`):
            Target execution graph.
        session_id (`str`):
            Session identifier stored on the variable node.
        filename (`str`):
            Source file recorded on the variable node (call-site attribution).
        lineno (`int`):
            Source line recorded on the variable node.
        id_strategy (`Callable[[T], str] | str | None`, optional):
            An identity strategy. It can be a callable, a registered name.
            If not provided, it will be looked up by type.
        encoding_fn (`Callable[[T], str] | None`, optional):
            Custom encoder from the value to string. 
        decoding_fn (`Callable[[str], T] | None`, optional):
            Optional decoder paired with the encoding function for the runtime handle.
        schema (`type[BaseModel] | None`, optional):
            Pydantic schema for auto encoding and decoding.
        comment (`str | None`, optional):
            A comment for the variable.
        category (`str`, defaults to `"variable"`):
            Variable category. 
        class_name (`str | None`, optional):
            Namespace prefix for the variable's full name when set.
        auto_class_name (`bool`, defaults to `False`):
            If enabled, it will auto-detect the class name from the value.
        variable_name (`str | None`, optional):
            If provided, it registers the returned handle on the current
            tracing context under this name (overwriting any prior registration).
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata for the variable.
        identity_only (`bool`, defaults to `False`):
            When enabled, the snapshot consistency check is bypassed for this
            variable.  If a node with the same identity already exists in the
            graph but has a different encoded value, the existing node is
            returned as-is instead of raising error or creating a new version.  
            This is useful when the caller holds a lightweight representation 
            (e.g. only an identifier) of a variable that was previously recorded 
            with a richer snapshot.
        force_new_version (`bool`, defaults to `False`):
            When enabled, it always creates a new version even if the encoded
            value matches the latest node.  It is used by ``comment_op`` to avoid
            self-loop edges when the same value appears in both inputs and outputs.

    Returns:
        `RuntimeVariable[T]`:
            A handle for the latest or newly created variable version.

    Raises:
        ValueError:
            If identity resolution yields the reserved NONE sentinel identity.
        TraceConsistencyError:
            If the graph is in strict mode, an existing node for this identity
            has a different encoded value, ``identity_only`` is not set, and
            the change was not recorded via ``comment_mutation``.
    """
    if auto_class_name and class_name is None:
        class_name = type(value).__qualname__

    # Determine the string representation.
    if schema is not None and encoding_fn is None:
        value_str = value.model_dump_json()
    elif encoding_fn is not None:
        value_str = encoding_fn(value)
    else:
        logger.debug(
            "No encoding function is provided. `repr` is used to encode the value.",
        )
        value_str = repr(value)

    name = _resolve_identity(value, id_strategy=id_strategy)
    full_name = f"{class_name}:{name}" if class_name is not None else name

    # Acquire the driver lock (if present) to make the read-modify-write
    # sequence atomic.
    # Drivers without a lock are assumed to handle concurrency internally.
    driver_lock = getattr(graph._driver, "_lock", None)
    lock_ctx = driver_lock if driver_lock is not None else contextlib.nullcontext()

    with lock_ctx:
        # Check if this variable already exists in the graph.
        raw = graph._driver.get_latest_node(full_name)
        if raw is None:
            existing = None
        else:
            existing = RuntimeVariable(variable=raw)

        if existing is not None and existing.raw_value == value_str and not force_new_version:
            rv_existing = RuntimeVariable(
                variable=existing._variable,
                encoding_fn=encoding_fn,
                decoding_fn=decoding_fn,
                schema=schema,
            )
            if variable_name is not None:
                ctx = current_context()
                assert ctx is not None, (
                    "The current tracing context is not active."
                )
                ctx.register_variable(variable_name, rv_existing, overwrite=True)
            return rv_existing

        if existing is not None and existing.raw_value != value_str and identity_only:
            logger.debug(
                "For the variable with the identity '{full_name}', "
                "a snapshot mismatch is detected. "
                "However, the caller explicitly opts out of snapshot consistency. "
                "Therefore, the existing node will be returned instead of raising " 
                "an error or creating a new version.",
                full_name=full_name,
            )
            rv_existing = RuntimeVariable(
                variable=existing._variable,
                encoding_fn=encoding_fn,
                decoding_fn=decoding_fn,
                schema=schema,
            )
            if variable_name is not None:
                ctx = current_context()
                assert ctx is not None, (
                    "The current tracing context is not active."
                )
                ctx.register_variable(variable_name, rv_existing, overwrite=True)
            return rv_existing

        # Strict mode check whether the value changed for an existing identity.
        if existing is not None and existing.raw_value != value_str:
            if graph.strict:
                raise TraceConsistencyError(
                    user_value=value,
                    user_value_encoded=value_str,
                    existing_variable=existing,
                    identity_name=name,
                )
            else:
                old_snippet, new_snippet = _diff_context(existing.raw_value, value_str)
                logger.info(
                    "A value changed for an existing identity (identity_name={name}) "
                    "but strict mode is disabled. A new version will be created. "
                    "The first difference between the recorded and provided values is:\n"
                    "  Recorded: {old}\n"
                    "  Provided: {new}",
                    name=name,
                    old=old_snippet,
                    new=new_snippet,
                )

        # Determine the version. 
        version = 1
        if existing is not None:
            version = existing.version + 1

        var = Variable(
            name=name,
            version=version,
            value=value_str,
            comment=comment,
            category=category,
            class_name=class_name,
            graph_id=graph.graph_id,
            user_id=graph.user_id,
            project_id=graph.project_id,
            session_id=session_id,
            filename=filename,
            lineno=lineno,
        )
        if metadata:
            var.update_metadata(metadata)

        # Propagate context metadata.
        ctx = current_context()
        assert ctx is not None, (
            "The current tracing context is not active."
        )
        ctx_meta = ctx.metadata
        if ctx_meta:
            var.update_metadata(ctx_meta)

        # Add the raw variable to the driver and build one runtime variable handle.
        graph._driver.add_node(var)

    rv_full = RuntimeVariable(
        variable=var,
        encoding_fn=encoding_fn,
        decoding_fn=decoding_fn,
        schema=schema,
    )

    # Register in context if a variable name is provided.
    if variable_name is not None:
        ctx.register_variable(variable_name, rv_full, overwrite=True)

    return rv_full


def _resolve_item(
    item: Any,
    *,
    shared_id_strategy: Callable[[Any], str] | str | None,
    shared_encoding_fn: Callable[[Any], str] | None,
    shared_decoding_fn: Callable[[str], Any] | None,
    shared_schema: type[BaseModel] | None,
    shared_auto_class_name: bool,
    shared_category: str,
    shared_metadata: dict[str, JsonValue] | None,
    graph: ExecNetwork,
    session_id: str,
    filename: str,
    lineno: int,
    force_new_version: bool = False,
) -> RuntimeVariable[Any]:
    """Resolve a single ``comment_op`` or ``comment_fn`` slot to a runtime variable.

    If ``item`` is already a ``RuntimeVariable``, it is returned unchanged.
    If ``item`` is a plain Python value, it is passed to :func:`_ensure_variable`
    with the shared keyword defaults from the caller.  If ``item`` is a length-2
    tuple ``(value, options)`` and ``options`` is a ``dict``, keys in that dict
    override the shared defaults for that slot only (for example
    ``id_strategy``, ``encoding_fn``, ``metadata``).  At debug level, tuple
    items log a truncated ``repr`` of ``value`` and the full options dict.

    Args:
        item (`Any`):
            A runtime handle, a raw value, or ``(value, options_dict)``.
        shared_id_strategy (`Callable[[Any], str] | str | None`):
            Default identity strategy when the item does not override it.
        shared_encoding_fn (`Callable[[Any], str] | None`):
            Default encoder when the item does not override it.
        shared_decoding_fn (`Callable[[str], Any] | None`):
            Default decoder when the item does not override it.
        shared_schema (`type[BaseModel] | None`):
            Default Pydantic schema when the item does not override it.
        shared_auto_class_name (`bool`):
            Default flag for auto class name detection.
        shared_category (`str`):
            Default variable category for newly created nodes.
        shared_metadata (`dict[str, JsonValue] | None`):
            Default metadata merged into new variable nodes when not overridden
            per item.
        graph (`ExecNetwork`):
            Target execution graph.
        session_id (`str`):
            Session identifier for new variable nodes.
        filename (`str`):
            Call-site file path for new variable nodes.
        lineno (`int`):
            Call-site line number for new variable nodes.
        force_new_version (`bool`, defaults to ``False``):
            When enabled, forwarded to :func:`_ensure_variable` so a new
            version is always created even if the encoded value matches the
            latest node.

    Returns:
        `RuntimeVariable[Any]`:
            The existing handle or a handle for the latest or newly created node.

    Raises:
        `ValueError`:
            If identity resolution yields the reserved NONE sentinel identity.
        `TraceConsistencyError`:
            If the graph is in strict mode and an existing identity's encoded
            value changed without ``comment_mutation``.
    """
    if isinstance(item, RuntimeVariable):
        return item

    config = {}
    value = item

    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
        value, config = item

        value_str = repr(value)
        if len(value_str) > 30:
            value_str = value_str[:27] + "..."
        logger.debug(
            "A value-option tuple is provided for an input or output item. "
            "The options will override the shared defaults.\n"
            "  Value: {value!r}\n"
            "  Options: {config!r}",
            value=value_str,
            config=config,
        )

    return _ensure_variable(
        value,
        id_strategy=config.get("id_strategy", shared_id_strategy),
        encoding_fn=config.get("encoding_fn", shared_encoding_fn),
        decoding_fn=config.get("decoding_fn", shared_decoding_fn),
        schema=config.get("schema", shared_schema),
        comment=config.get("comment"),
        category=config.get("category", shared_category),
        class_name=config.get("class_name"),
        auto_class_name=config.get("auto_class_name", shared_auto_class_name),
        variable_name=config.get("variable_name"),
        metadata=config.get("metadata", shared_metadata),
        identity_only=config.get("identity_only", False),
        graph=graph,
        session_id=session_id,
        filename=filename,
        lineno=lineno,
        force_new_version=force_new_version,
    )