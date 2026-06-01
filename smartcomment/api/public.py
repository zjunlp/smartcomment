"""Public API for smartcomment, the ``comment_*`` family of functions."""

import asyncio
import functools
import inspect
from pydantic import BaseModel, JsonValue
from ..runtime import (
    none_full_node_id,
    none_op_id,
    none_session_id,
    current_graph, 
    current_context,
    current_op,
    current_session, 
    is_tracing_enabled, 
)
from ..runtime.context import _OP
from ..runtime.operation import RuntimeEdge, RuntimeOp
from ..runtime.variable import RuntimeVariable
from ..schema.operation import OpEdge, OpRecord
from ..logging import logger
from ._mutation import _MutationScope
from ._helpers import (
    _resolve_call_context, 
    _ensure_variable,
    _resolve_item,
)
from typing import (
    Any,
    Callable,
    Literal,
    TypeVar,
    overload,
)


T = TypeVar("T")


@overload
def comment_variable(
    value: T,
    *,
    to_runtime: Literal[True],
    variable_name: str | None = ...,
    encoding_fn: Callable[[T], str] | None = ...,
    decoding_fn: Callable[[str], T] | None = ...,
    schema: type[BaseModel] | None = ...,
    id_strategy: Callable[[T], str] | str | None = ...,
    comment: str | None = ...,
    category: str = ...,
    class_name: str | None = ...,
    auto_class_name: bool = ...,
    identity_only: bool = ...,
    metadata: dict[str, JsonValue] | None = ...,
) -> RuntimeVariable[T]: ...


@overload
def comment_variable(
    value: T,
    *,
    to_runtime: Literal[False] = ...,
    variable_name: str | None = ...,
    encoding_fn: Callable[[T], str] | None = ...,
    decoding_fn: Callable[[str], T] | None = ...,
    schema: type[BaseModel] | None = ...,
    id_strategy: Callable[[T], str] | str | None = ...,
    comment: str | None = ...,
    category: str = ...,
    class_name: str | None = ...,
    auto_class_name: bool = ...,
    identity_only: bool = ...,
    metadata: dict[str, JsonValue] | None = ...,
) -> T: ...


def comment_variable(
    value: T,
    *,
    to_runtime: bool = False,
    variable_name: str | None = None,
    encoding_fn: Callable[[T], str] | None = None,
    decoding_fn: Callable[[str], T] | None = None,
    schema: type[BaseModel] | None = None,
    id_strategy: Callable[[T], str] | str | None = None,
    comment: str | None = None,
    category: str = "variable",
    class_name: str | None = None,
    auto_class_name: bool = False,
    identity_only: bool = False,
    metadata: dict[str, JsonValue] | None = None,
) -> RuntimeVariable[T] | T:
    """Register a value as a tracked variable in the execution graph.

    Use this for starting variables (no parent operation) or when you
    need to store the handle in the current tracing context for cross-scope
    access.

    When no session is active the variable is placed under the reserved
    NONE sentinel session.

    Args:
        value (`T`):
            The Python value to track.
        to_runtime (`bool`, defaults to `False`):
            When enabled, a runtime variable handle is returned.
            Otherwise, the original variable is returned after it has been 
            recorded in the graph.
        variable_name (`str | None`, optional):
            If provided, it registers the handle in the current tracing context
            so the variable can be retrieved by name in inner scopes.
        encoding_fn (`Callable[[T], str] | None`, optional):
            Custom encoder from Python value to string.
        decoding_fn (`Callable[[str], T] | None`, optional):
            Custom decoder from string back to Python value.
        schema (`type[BaseModel] | None`, optional):
            Pydantic schema for auto encoding and decoding.
        id_strategy (`Callable[[T], str] | str | None`, optional):
            An identity strategy. It can be a callable, a registered name.
            If not provided, it will be looked up by type.
        comment (`str | None`, optional):
            A comment for the variable.
        category (`str`, defaults to `"variable"`):
            Variable category. 
        class_name (`str | None`, optional):
            Namespace from the Python class of the value.
        auto_class_name (`bool`, defaults to `False`):
            If enabled, it will auto-detect the class name from the value.
        identity_only (`bool`, defaults to `False`):
            When enabled, the snapshot consistency check is bypassed for
            this variable. If a node with the same identity already exists
            in the graph but has a different encoded value, the existing
            node is returned instead of raising an error or creating a new 
            version. This is useful when the caller only holds a lightweight
            representation (e.g. an identifier) of a variable that was
            previously recorded with a richer snapshot.
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata for the variable.

    Returns:
        `RuntimeVariable[T] | T`:
            The runtime handle when ``to_runtime`` is enabled, or the
            original variable otherwise.  It always returns the original 
            variable when the tracing is disabled.
    """
    if not is_tracing_enabled():
        return value  # type: ignore[return-value]

    if isinstance(value, RuntimeVariable):
        if variable_name is not None:
            ctx = current_context()
            assert ctx is not None, (
                "The current tracing context is not active."
            )

            logger.debug(
                "`comment_variable` receives a runtime variable handle as the value. "
                "It will be registered in the current tracing context " 
                "under the name '{variable_name}'.",
                variable_name=variable_name,
            )
            ctx.register_variable(variable_name, value, overwrite=True)
        return value  # type: ignore[return-value]

    graph, session_id, filename, lineno = _resolve_call_context(
        caller_name="comment_variable",
    )

    rv = _ensure_variable(
        value,
        id_strategy=id_strategy,
        encoding_fn=encoding_fn,
        decoding_fn=decoding_fn,
        schema=schema,
        comment=comment,
        category=category,
        class_name=class_name,
        auto_class_name=auto_class_name,
        variable_name=variable_name,
        metadata=metadata,
        identity_only=identity_only,
        graph=graph,
        session_id=session_id,
        filename=filename,
        lineno=lineno,
        force_new_version=False, 
    )

    if to_runtime:
        return rv
    return value


def comment_op(
    *,
    inputs: list[Any],
    outputs: list[Any],
    op_name: str | None = None,
    comment: str | None = None,
    category: str = "operation",
    id_strategy: Callable[[Any], str] | str | None = None,
    encoding_fn: Callable[[Any], str] | None = None,
    decoding_fn: Callable[[str], Any] | None = None,
    schema: type[BaseModel] | None = None,
    auto_class_name: bool = False,
    metadata: dict[str, JsonValue] | None = None,
    reuse_op: bool = False,
) -> RuntimeOp | None:
    """Record an operation that links input variables to output variables.

    Each element in ``inputs`` and ``outputs`` is interpreted in one of three
    ways.  If the entry is already a runtime variable handle, that handle is
    wired into the graph as given.  If it is an ordinary Python value, a
    variable node is created or reused using the same encoding and identity
    rules as ``comment_variable``, using the shared parameters of this call
    (``id_strategy``, ``encoding_fn``, and so on) as defaults.  If it is a 
    value-option tuple where the first element is the value and the second is
    a dictionary of per-item options, those keys in each option dictionary override
    the shared defaults. For available options for each variable, please
    refer to ``comment_variable``.

    When ``inputs`` or ``outputs`` is empty, the NONE sentinel is
    auto-injected so that graph edges always exist.

    Args:
        inputs (`list[Any]`):
            Input items.
        outputs (`list[Any]`):
            Output items.
        op_name (`str | None`, optional):
            Canonical operation name.  When not provided, an active
            operation context is required and its operation is reused.
        comment (`str | None`, optional):
            A comment for the operation.
        category (`str`, defaults to `"operation"`):
            Operation category.
        id_strategy (`Callable[[Any], str] | str | None`, optional):
            Shared identity strategy for auto-created variables.
        encoding_fn (`Callable[[Any], str] | None`, optional):
            Shared encoder for auto-created variables.
        decoding_fn (`Callable[[str], Any] | None`, optional):
            Shared decoder for auto-created variables.
        schema (`type[BaseModel] | None`, optional):
            Shared Pydantic schema for auto encoding and decoding.
        auto_class_name (`bool`, defaults to `False`):
            Auto-detect class name for auto-created variables.
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata merged into the operation record and corresponding 
            operation edges. It is also used as the default for auto-created variables.  
            To attach metadata to a specific variable instead of sharing this 
            dictionary, pass that slot as ``(value, {"metadata": ...})`` 
            inside ``inputs``.
        reuse_op (`bool`, defaults to `False`):
            When enabled and an active operation context exists, edges are
            attributed to the existing operation instead of creating a new
            one.  The ``category``, ``comment``, and ``metadata`` are applied
            to the edges only. 

    Returns:
        `RuntimeOp | None`:
            A runtime view of the operation, or ``None`` if tracing is
            disabled.

    Raises:
        `RuntimeError`:
            If the operation name is not provided and no active operation context
            exists.
    """
    if not is_tracing_enabled():
        return None

    graph, session_id, filename, lineno = _resolve_call_context(
        caller_name="comment_op",
    )

    # Resolve the operation before creating any variable nodes so that a
    # failure does not leave orphan nodes in the driver.
    ctx = current_context()
    assert ctx is not None, (
        "The current tracing context is not active."
    )

    propagated = ctx.metadata

    should_try_reuse = op_name is None or reuse_op
    active_op = current_op() if should_try_reuse else None

    if active_op is not None:
        op = active_op
    elif op_name is None:
        raise RuntimeError(
            "`comment_op` requires either an explicit operation name or an "
            "active operation context.  When the operation name is not provided, "
            "please wrap the call in `with comment_op_scope(op_name=...) as op:`."
        )
    else:
        op = OpRecord(
            graph_id=graph.graph_id,
            session_id=session_id,
            user_id=graph.user_id,
            project_id=graph.project_id,
            op_name=op_name,
            comment=comment,
            category=category,
            filename=filename,
            lineno=lineno,
        )
        if metadata:
            op.update_metadata(metadata)
        if propagated:
            op.update_metadata(propagated)
        graph._driver.add_operation(op)

    resolve_kwargs = dict(
        shared_id_strategy=id_strategy,
        shared_encoding_fn=encoding_fn,
        shared_decoding_fn=decoding_fn,
        shared_schema=schema,
        shared_auto_class_name=auto_class_name,
        shared_category="variable",
        shared_metadata=metadata,
        graph=graph,
        session_id=session_id,
        filename=filename,
        lineno=lineno,
    )

    # Resolve input items first so we can detect self-loops in outputs.
    input_rvs = [_resolve_item(item, **resolve_kwargs) for item in inputs]
    input_node_ids = {rv.full_node_id for rv in input_rvs}

    # Resolve output items. 
    # If an output resolves to the same node as an input, 
    # force a new version to prevent self-loop edges.
    output_rvs = []
    for item in outputs:
        # Resolve each output to a runtime variable.  When an output would resolve to
        # the same graph node as an already-resolved input (same identity and encoded
        # value), the first resolution returns that existing node. 
        rv = _resolve_item(item, **resolve_kwargs)
        if rv.full_node_id in input_node_ids:
            logger.warning(
                "Output collides with an input node whose full name is '{!r}' " 
                "in the operation named '{}'. "
                "A new variable version is created and edges are added. This is valid "
                "but non-idiomatic and increases graph complexity.",
                rv.full_name, 
                op_name,
            )

            # We then call `_resolve_item` again with `force_new_version=True` 
            # so a new variable version is created, avoiding a self-loop edge 
            # from the node to itself while still recording edges from inputs to this output.
            rv = _resolve_item(item, force_new_version=True, **resolve_kwargs)
        output_rvs.append(rv)

    runtime_op = RuntimeOp(op=op)

    if not input_rvs and not output_rvs:
        logger.debug(
            "No input or output variables are provided for the operation named '{}'.",
            op_name,
        )
        return runtime_op

    # NONE sentinel injection.
    if not input_rvs or not output_rvs:
        graph._ensure_none_node()

    # Build two lists of source and target full node identifiers.
    _none = none_full_node_id()
    source_ids = [rv.full_node_id for rv in input_rvs] if input_rvs else [_none]
    target_ids = [rv.full_node_id for rv in output_rvs] if output_rvs else [_none]

    # Pre-compute merged metadata for edges.
    edge_metadata = {}
    if metadata:
        edge_metadata.update(metadata)
    if propagated:
        edge_metadata.update(propagated)

    # Create edges (cartesian product).
    for src in source_ids:
        for tgt in target_ids:
            edge = OpEdge(
                graph_id=graph.graph_id,
                session_id=session_id,
                user_id=graph.user_id,
                project_id=graph.project_id,
                op_id=op.op_id,
                category=category,
                source_full_node_id=src,
                target_full_node_id=tgt,
                comment=comment,
                filename=filename,
                lineno=lineno,
            )
            if edge_metadata:
                edge.update_metadata(edge_metadata)
            graph._driver.add_edge(edge)

    return runtime_op


def comment_mutation(
    *,
    target: T,
    inputs: list[Any] | None = None,
    comment: str | None = None,
    category: str = "variable",
    class_name: str | None = None,
    auto_class_name: bool = False,
    id_strategy: Callable[[Any], str] | str | None = None,
    encoding_fn: Callable[[Any], str] | None = None,
    decoding_fn: Callable[[str], Any] | None = None,
    schema: type[BaseModel] | None = None,
    mutation_name: str | None = None,
    mutation_comment: str | None = None,
    mutation_category: str = "mutation",
    metadata: dict[str, JsonValue] | None = None,
    mutation_metadata: dict[str, JsonValue] | None = None,
    reuse_op: bool = False,
) -> _MutationScope[T]:
    """Context manager that records an in-place mutation as a new version.

    It wraps the code that mutates a target variable inside the ``with``
    block.  On entry, the current state of target is snapshotted.  On
    normal exit, the target is re-encoded and a new version node, an
    operation record, and connecting edges are written to the graph.

    ``target`` must be a mutable Python object. Passing a
    runtime variable raises an error because it is a read-only
    view and mutating it would violate tracing invariants.

    Example::

        with comment_mutation(target=my_list, mutation_name="append") as scope:
            my_list.append("new_item")
        new_rv = scope.result   # RuntimeVariable for the new version

    Args:
        target (`T`):
            The mutable Python object to track.
        inputs (`list[Any] | None`, optional):
            Additional input variables involved in the mutation.  Each
            element may be a raw value, a runtime variable, or a
            value-option tuple whose dict keys override the
            shared defaults (``id_strategy``, ``encoding_fn``, etc.).
        comment (`str | None`, optional):
            Comment attached to the target variable (the new version
            node).  For the operation comment, use `mutation_comment`.
        category (`str`, defaults to `"variable"`):
            Category for the target variable node.  Also used as the
            shared default for input variables that do not override it.
        class_name (`str | None`, optional):
            Namespace prefix for the target variable's full name.
        auto_class_name (`bool`, defaults to `False`):
            Auto-detect `class_name` from the target's Python type.
        id_strategy (`Callable[[Any], str] | str | None`, optional):
            Identity strategy for the target variable.  Also used as the
            shared default for input variables that do not override it.
        encoding_fn (`Callable[[Any], str] | None`, optional):
            Encoder for the target and input variables (shared default).
        decoding_fn (`Callable[[str], Any] | None`, optional):
            Decoder paired with the encoding function (shared default).
        schema (`type[BaseModel] | None`, optional):
            Pydantic schema for auto encoding and decoding (shared default).
        mutation_name (`str | None`, optional):
            Canonical operation name. If not provided, it will be auto-generated 
            from the target variable's full name.
        mutation_comment (`str | None`, optional):
            Comment attached to the operation record and propagated
            to the version edge and input edges. If not provided, the 
            version edge will use the default comment.
        mutation_category (`str`, defaults to `"mutation"`):
            Category for the operation record and edges.
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata attached to the target variable (the new
            version node). 
        mutation_metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata attached to the operation record.  Edges
            also receive a copy.
        reuse_op (`bool`, defaults to `False`):
            When enabled and an active operation context exists, edges
            are attributed to the existing operation instead of creating a
            new mutation operation.  The ``mutation_comment`` and
            ``mutation_category`` are still applied to the edges.  The
            version bump (new variable node) always happens regardless
            of this flag.  When no active operation context is found,
            a new mutation operation is created as usual.

    Returns:
        `_MutationScope[T]`:
            A context manager for the in-place mutation operation.

    Raises:
        `ValueError`:
            If target variable is a runtime variable or an input collides
            with the target's full node identifier.
        `RuntimeError`:
            If no graph context is active.
    """
    if isinstance(target, RuntimeVariable):
        raise ValueError(
            "`comment_mutation` does not accept a runtime variable as "
            "target because it is a read-only view.  Pass the mutable "
            "Python object directly."
        )

    return _MutationScope(
        target=target,
        inputs=inputs,
        comment=comment,
        category=category,
        class_name=class_name,
        auto_class_name=auto_class_name,
        id_strategy=id_strategy,
        encoding_fn=encoding_fn,
        decoding_fn=decoding_fn,
        schema=schema,
        mutation_name=mutation_name,
        mutation_comment=mutation_comment,
        mutation_category=mutation_category,
        metadata=metadata,
        mutation_metadata=mutation_metadata,
        reuse_op=reuse_op,
    )


def comment_fn(
    *,
    op_name: str | None = None,
    comment: str | None = None,
    category: str = "operation",
    id_strategy: Callable[[Any], str] | str | None = None,
    encoding_fn: Callable[[Any], str] | None = None,
    decoding_fn: Callable[[str], Any] | None = None,
    schema: type[BaseModel] | None = None,
    auto_class_name: bool = False,
    op_metadata: dict[str, JsonValue] | None = None,
    metadata: dict[str, JsonValue] | None = None,
    param_options: dict[str, dict[str, Any]] | None = None,
    include_source: bool = False,
) -> Callable:
    """Decorator for automatically tracing function-level calls.

    It wraps a synchronous or asynchronous function so that every call records
    an operation with the function arguments as inputs and the return value as
    a single output.

    When an active operation context is present, the edges created by this
    decorator are attributed to that existing operation (the ``category`` and
    ``comment`` are applied to each edge only).  When no operation context is
    active, a new operation record is created and installed as the active
    operation context for the duration of the function body, so that inner calls to
    ``comment_link`` can reference it.

    Per-parameter options are configured via ``param_options``, a dictionary
    mapping parameter names to option dictionaries. Unmentioned parameters
    use the shared defaults supplied to this decorator. To configure the output, 
    you can pass the key ``"-o"`` together with its option dictionary. 

    Example::

        @comment_fn(
            category="extraction",
            param_options={
                "query": {"id_strategy": "content"},
                "entries": {"auto_class_name": True},
            },
        )
        def extract(query: str, entries: list) -> list:
            ...

        @comment_fn(op_name="async_op")
        async def fetch(url: str) -> str:
            ...

        # Reusing an outer operation scope:
        with comment_op_scope(op_name="pipeline") as op:
            result = extract(query, entries)

    Args:
        op_name (`str | None`, optional):
            Canonical operation name recorded in the graph. When not
            provided, the decorated function's qualified name is used.
        comment (`str | None`, optional):
            Static operation description. When not provided, the decorated
            function's docstring is used. If the function has no docstring,
            its qualified name is used as a fallback.
        category (`str`, defaults to `"operation"`):
            Operation category. It is applied to the operation record when a new
            one is created, and always applied to every edge.
        id_strategy (`Callable[[Any], str] | str | None`, optional):
            Shared identity strategy for auto-created input and output variables.
        encoding_fn (`Callable[[Any], str] | None`, optional):
            Shared encoder for auto-created variables.
        decoding_fn (`Callable[[str], Any] | None`, optional):
            Shared decoder for auto-created variables.
        schema (`type[BaseModel] | None`, optional):
            Shared Pydantic schema for auto encoding and decoding.
        auto_class_name (`bool`, defaults to ``False``):
            Auto-detect class name for auto-created variables.
        op_metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata attached to the operation record (when created)
            and its edges.
        metadata (`dict[str, JsonValue] | None`, optional):
            Shared default metadata for auto-created variable nodes.
        param_options (`dict[str, dict[str, Any]] | None`, optional):
            Per-parameter option overrides. Keys are parameter names, values
            are option dicts whose keys override the shared defaults for that
            parameter only. If you want to configure the output, you can
            pass the key ``"-o"`` together with its option dict, which is
            applied to the output variable instead of an input parameter. 
        include_source (`bool`, defaults to ``False``):
            When enabled, the decorated function's source code is captured
            and attached as ``"source_code"`` in every edge's metadata.

    Returns:
        `Callable`:
            The decorated function (sync or async, matching the original).
    """
    opts_map = param_options or {}

    def decorator(fn: Callable) -> Callable:
        sig = inspect.signature(fn)

        resolved_op_name = op_name if op_name is not None else fn.__qualname__
        if comment is not None:
            auto_comment = comment
        else:
            # If the user writes a docstring, we use it as the comment.
            docstring = inspect.getdoc(fn)
            if docstring:
                auto_comment = f"[{fn.__qualname__}] {inspect.cleandoc(docstring)}"
            else:
                # Otherwise, we use the qualified name as the comment.
                auto_comment = fn.__qualname__

        fn_source = None
        if include_source:
            try:
                fn_source = inspect.getsource(fn)
            except Exception as e:
                logger.warning(
                    "It is unable to get the source code for {}.\n" 
                    "Below is the error information:\n\n"
                    "  {}\n", 
                    fn.__qualname__,
                    e,
                )
                fn_source = None

        fn_filename = fn.__code__.co_filename
        fn_lineno = fn.__code__.co_firstlineno

        def _resolve_session_id(graph):
            """Return the active session identifier or fall back to the NONE sentinel."""
            session = current_session()
            if session is not None:
                return session.session_id
            graph._ensure_none_session()
            return none_session_id()

        def _setup_op(graph, session_id):
            """Create or reuse an operation.

            When an active operation context is present, its operation is
            reused.  Otherwise a fresh operation record is created, persisted during 
            the function body.
            """
            active_op = current_op()
            if active_op is not None:
                return active_op, None, True

            fn_ctx = current_context()
            assert fn_ctx is not None, (
                "The current tracing context is not active."
            )

            op = OpRecord(
                graph_id=graph.graph_id,
                session_id=session_id,
                user_id=graph.user_id,
                project_id=graph.project_id,
                op_name=resolved_op_name,
                comment=auto_comment,
                category=category,
                filename=fn_filename,
                lineno=fn_lineno,
            )

            merged = {}
            if op_metadata:
                merged.update(op_metadata)
            propagated = fn_ctx.metadata
            if propagated:
                merged.update(propagated)
            if merged:
                op.update_metadata(merged)

            graph._driver.add_operation(op)
            token = _OP.set(op)
            return op, token, False

        def _trace_edges(result, bound, op, graph, session_id):
            """Resolve input, output variables, and write edges."""
            input_items = []

            # We iterate over the arguments and create a list of input variables.
            for name, value in bound.arguments.items():
                per_param = opts_map.get(name)
                if per_param is not None:
                    input_items.append((value, per_param))
                else:
                    input_items.append(value)

            # The reserved `"-o"` key configures the output variable.
            output_items = []
            if result is not None:
                output_opts = opts_map.get("-o")
                if output_opts is not None:
                    output_items.append((result, output_opts))
                else:
                    output_items.append(result)

            resolve_kwargs = dict(
                shared_id_strategy=id_strategy,
                shared_encoding_fn=encoding_fn,
                shared_decoding_fn=decoding_fn,
                shared_schema=schema,
                shared_auto_class_name=auto_class_name,
                shared_category="variable",
                shared_metadata=metadata,
                graph=graph,
                session_id=session_id,
                filename=fn_filename,
                lineno=fn_lineno,
            )

            input_rvs = [_resolve_item(item, **resolve_kwargs) for item in input_items]
            output_rvs = [_resolve_item(item, **resolve_kwargs) for item in output_items]

            if not input_rvs and not output_rvs:
                logger.debug(
                    "No input or output variables for operation '{}'.",
                    resolved_op_name,
                )
                return

            if not input_rvs or not output_rvs:
                graph._ensure_none_node()

            fn_ctx = current_context()
            assert fn_ctx is not None, (
                "The current tracing context is not active."
            )

            edge_meta = {}
            if op_metadata:
                edge_meta.update(op_metadata)
            if fn_source is not None:
                edge_meta["source_code"] = fn_source
            propagated = fn_ctx.metadata
            if propagated:
                edge_meta.update(propagated)

            _none = none_full_node_id()
            source_ids = [rv.full_node_id for rv in input_rvs] if input_rvs else [_none]
            target_ids = [rv.full_node_id for rv in output_rvs] if output_rvs else [_none]

            for src in source_ids:
                for tgt in target_ids:
                    edge = OpEdge(
                        graph_id=graph.graph_id,
                        session_id=session_id,
                        user_id=graph.user_id,
                        project_id=graph.project_id,
                        op_id=op.op_id,
                        category=category,
                        source_full_node_id=src,
                        target_full_node_id=tgt,
                        comment=auto_comment,
                        filename=fn_filename,
                        lineno=fn_lineno,
                    )
                    if edge_meta:
                        edge.update_metadata(edge_meta)
                    graph._driver.add_edge(edge)

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not is_tracing_enabled():
                    return await fn(*args, **kwargs)
                graph = current_graph()
                if graph is None:
                    return await fn(*args, **kwargs)

                session_id = _resolve_session_id(graph)
                op, token, _reused = _setup_op(graph, session_id)
                try:
                    result = await fn(*args, **kwargs)
                finally:
                    if token is not None:
                        _OP.reset(token)

                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                _trace_edges(result, bound, op, graph, session_id)
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not is_tracing_enabled():
                    return fn(*args, **kwargs)
                graph = current_graph()
                if graph is None:
                    return fn(*args, **kwargs)

                session_id = _resolve_session_id(graph)
                op, token, _reused = _setup_op(graph, session_id)
                try:
                    result = fn(*args, **kwargs)
                finally:
                    if token is not None:
                        _OP.reset(token)

                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                _trace_edges(result, bound, op, graph, session_id)
                return result
            return sync_wrapper

    return decorator


def comment_link(
    *,
    source: Any,
    target: Any,
    comment: str | None = None,
    category: str | None = None,
    id_strategy: Callable[[Any], str] | str | None = None,
    encoding_fn: Callable[[Any], str] | None = None,
    decoding_fn: Callable[[str], Any] | None = None,
    schema: type[BaseModel] | None = None,
    auto_class_name: bool = False,
    metadata: dict[str, JsonValue] | None = None,
    edge_metadata: dict[str, JsonValue] | None = None,
) -> RuntimeEdge | None:
    """Record a single directed edge between two variables.

    Unlike ``comment_op`` which creates a Cartesian product of edges
    between all inputs and all outputs, ``comment_link`` creates exactly
    one edge from one source variable to one target variable.  This allows 
    fine-grained control over graph topology within the same operation scope.

    If an active operation context exists, the edge is associated with that 
    operation and inherits its category and comment as defaults. 
    When no operation context is active, a per-graph NONE sentinel operation 
    is lazily created.

    Note that if you want to specify the category and comment for the variable, 
    you should pass these as options to the variable or use ``comment_variable``.

    Example::

        with comment_op_scope(op_name="custom_links") as op:
            comment_link(source=query, target=result_a, category="primary")
            comment_link(source=query, target=result_b, category="secondary")

    Args:
        source (`Any`):
            The upstream variable. It can be a raw Python value, a runtime variable, 
            or a value-option tuple.
        target (`Any`):
            The downstream variable. It can be a raw Python value, a runtime variable, 
            or a value-option tuple.
        comment (`str | None`, optional):
            Edge annotation. When not provided, it falls back to the active
            operation's comment as default.
        category (`str | None`, optional):
            Edge category. When not provided, it falls back to the active
            operation's category as default, or `"link"` when no
            operation context is active.
        id_strategy (`Callable[[Any], str] | str | None`, optional):
            Shared identity strategy for auto-created variable nodes.
        encoding_fn (`Callable[[Any], str] | None`, optional):
            Shared encoder for auto-created variables.
        decoding_fn (`Callable[[str], Any] | None`, optional):
            Shared decoder for auto-created variables.
        schema (`type[BaseModel] | None`, optional):
            Shared Pydantic schema for auto encoding and decoding.
        auto_class_name (`bool`, defaults to `False`):
            Auto-detect class name for auto-created variables.
        metadata (`dict[str, JsonValue] | None`, optional):
            Metadata used as the default for auto-created variable nodes.
        edge_metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata attached to the created edge.

    Returns:
        `RuntimeEdge | None`:
            A runtime view of the created edge, or ``None`` if tracing is
            disabled.
    """
    if not is_tracing_enabled():
        return None

    graph, session_id, filename, lineno = _resolve_call_context(
        caller_name="comment_link",
    )

    resolve_kwargs = dict(
        shared_id_strategy=id_strategy,
        shared_encoding_fn=encoding_fn,
        shared_decoding_fn=decoding_fn,
        shared_schema=schema,
        shared_auto_class_name=auto_class_name,
        shared_category="variable",
        shared_metadata=metadata,
        graph=graph,
        session_id=session_id,
        filename=filename,
        lineno=lineno,
    )

    source_rv = _resolve_item(source, **resolve_kwargs)
    target_rv = _resolve_item(target, **resolve_kwargs)

    active_op = current_op()
    if active_op is not None:
        op_id = active_op.op_id
        resolved_category = category if category is not None else active_op.category
        resolved_comment = comment if comment is not None else active_op.comment
    else:
        graph._ensure_none_op()
        op_id = none_op_id()
        resolved_category = category if category is not None else "link"
        resolved_comment = comment

    ctx = current_context()
    assert ctx is not None, "The current tracing context is not active."

    merged_edge_metadata = {}
    if edge_metadata:
        merged_edge_metadata.update(edge_metadata)
    propagated = ctx.metadata
    if propagated:
        merged_edge_metadata.update(propagated)

    edge = OpEdge(
        graph_id=graph.graph_id,
        session_id=session_id,
        user_id=graph.user_id,
        project_id=graph.project_id,
        op_id=op_id,
        category=resolved_category,
        source_full_node_id=source_rv.full_node_id,
        target_full_node_id=target_rv.full_node_id,
        comment=resolved_comment,
        filename=filename,
        lineno=lineno,
    )
    if merged_edge_metadata:
        edge.update_metadata(merged_edge_metadata)
    graph._driver.add_edge(edge)

    return RuntimeEdge(edge=edge)
