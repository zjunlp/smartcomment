"""The tracing context and context manager functions for smartcomment."""

import re
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from pydantic import JsonValue, PrivateAttr
from .network import ExecNetwork, none_session_id
from .operation import RuntimeOp
from .session import RuntimeSession
from .variable import RuntimeVariable
from ..schema.base import BaseMetadataModel
from ..schema.operation import OpRecord
from ..schema.session import Session
from ..logging import logger
from typing import (
    Any, 
    Iterator, 
    Iterable, 
)


# Module-level context variables (one per hierarchy level). 
_GRAPH: ContextVar[ExecNetwork | None] = ContextVar("_GRAPH", default=None)
_SESSION: ContextVar[Session | None] = ContextVar("_SESSION", default=None)
_OP: ContextVar[OpRecord | None] = ContextVar("_OP", default=None)

# Global toggle for tracing.
_TRACING_ENABLED: bool = True


class TracingContext(BaseMetadataModel):
    """Per-scope context that tracks runtime variables and propagates metadata.

    A tracing context is stored in the context variable and
    provides read-access to the current graph, session, and operation
    via properties that delegate to the module-level context variables.
    """

    _runtime_variables: dict[str, RuntimeVariable[Any]] = PrivateAttr(default_factory=dict)
    _full_node_id_to_names: dict[str, set[str]] = PrivateAttr(default_factory=dict)

    def register_variable(
        self,
        name: str,
        rv: RuntimeVariable[Any],
        overwrite: bool = False,
    ) -> None:
        """Register a runtime variable by user-chosen name.

        Args:
            name (`str`):
                Semantic name for the variable (e.g. a local variable name).
            rv (`RuntimeVariable[Any]`):
                The runtime handle.
            overwrite (`bool`, defaults to `False`):
                If it is not enabled, an error will be raised when the given name 
                is already registered. Otherwise, it will overwrite the existing variable.
        """
        if name in self._runtime_variables:
            if not overwrite:
                raise ValueError(
                    f"Variable name '{name}' is already registered in this context. "
                    f"Use `overwrite=True` to replace it."
                )

            logger.debug(
                "A variable with name '{name}' is already registered in this context. "
                "It will be overwritten.",
                name=name,
            )
            # Detach the name from the previous runtime variable's alias set.
            # This keeps the reverse index consistent when the old and new 
            # handles point to different full node identifiers.
            old_rv = self._runtime_variables[name]
            old_names = self._full_node_id_to_names[old_rv.full_node_id]
            old_names.discard(name)
            if not old_names:
                self._full_node_id_to_names.pop(old_rv.full_node_id)

        self._runtime_variables[name] = rv
        self._full_node_id_to_names.setdefault(rv.full_node_id, set()).add(name)

    def get_variable(self, name: str) -> RuntimeVariable[Any]:
        """Look up a runtime variable by its registered name.

        Args:
            name (`str`):
                The name used during registration.

        Returns:
            `RuntimeVariable`:
                The runtime handle.

        Raises:
            `NameError`:
                If the variable with the given name has not been declared in 
                this tracing context.
        """
        try:
            return self._runtime_variables[name]
        except KeyError:
            raise NameError(
                f"Variable name '{name}' is not declared in this tracing context."
            ) from None

    def get_variable_by_full_node_id(self, full_node_id: str) -> RuntimeVariable[Any]:
        """Look up a runtime variable by its full (namespaced) node identifier.

        Args:
            full_node_id (`str`):
                The full node identifier of the variable.

        Returns:
            `RuntimeVariable`:
                The runtime handle.

        Raises:
            `NameError`:
                If no variable with the given full node identifier is found.
        """
        names = self._full_node_id_to_names.get(full_node_id)
        if names is None:
            raise NameError(
                f"No variable with full node identifier '{full_node_id}' is "
                "registered in this tracing context."
            )
        return self._runtime_variables[next(iter(names))]

    def get_names_by_full_node_id(self, full_node_id: str) -> set[str]:
        """Return all names registered for the given full node identifier.

        Args:
            full_node_id (`str`):
                The full node identifier of the variable.

        Returns:
            `set[str]`:
                A fresh copy of the set of registered names. The returned set
                is empty when no variable with this identifier is registered.
        """
        names = self._full_node_id_to_names.get(full_node_id)
        if names is None:
            return set()
        return set(names)

    def remove_variable(self, name: str) -> RuntimeVariable[Any]:
        """Remove a runtime variable by its registered name.

        The variable is removed from the tracing context only. It is not
        deleted from the underlying execution graph or driver.

        Args:
            name (`str`):
                The name used during registration.

        Returns:
            `RuntimeVariable[Any]`:
                The removed runtime variable handle.

        Raises:
            `NameError`:
                If no variable with the given name is registered in this
                tracing context.
        """
        try:
            rv = self._runtime_variables.pop(name)
        except KeyError:
            raise NameError(
                f"Variable name '{name}' is not declared in this tracing context."
            ) from None

        names = self._full_node_id_to_names.get(rv.full_node_id)
        if names is not None:
            names.discard(name)
            if not names:
                self._full_node_id_to_names.pop(rv.full_node_id)
        return rv

    def query_variables(
        self,
        *,
        name_pattern: str | None = None,
        category: str | Iterable[str] | None = None,
        class_name: str | None = None,
    ) -> list[RuntimeVariable[Any]]:
        """Query registered runtime variables by public traits.

        All supplied filters are combined with logical AND. When no filters 
        are given, all registered variables are returned.

        Args:
            name_pattern (`str | None`, optional):
                Regular expression matched against the registered variable
                name.  Plain keywords are treated as literal substrings.
            category (`str | Iterable[str] | None`, optional):
                A single category string or a set of category strings.
                A variable matches if its category is contained in the set.
            class_name (`str | None`, optional):
                Exact class name to match.

        Returns:
            `list[RuntimeVariable[Any]]`:
                Variables satisfying all filters, ordered by registration
                insertion order.
        """
        compiled = re.compile(name_pattern) if name_pattern is not None else None
        cat_set = None
        if isinstance(category, str):
            cat_set = {category}
        elif category is not None:
            cat_set = set(category)

        results = []
        for registered_name, rv in self._runtime_variables.items():
            if compiled is not None and not compiled.search(registered_name):
                continue
            if cat_set is not None and rv.category not in cat_set:
                continue
            if class_name is not None and rv.class_name != class_name:
                continue
            results.append(rv)
        return results

    @property
    def graph(self) -> ExecNetwork | None:
        """Get the execution graph from the current context."""
        return _GRAPH.get()

    @property
    def session(self) -> Session | None:
        """Get the current session from the current context."""
        return _SESSION.get()

    @property
    def op(self) -> OpRecord | None:
        """Get the current operation from the current context."""
        return _OP.get()


# The current tracing context.
_TRACING_CTX: ContextVar[TracingContext | None] = ContextVar("_TRACING_CTX", default=None)


def enable_tracing() -> None:
    """Enable the global tracing toggle."""
    global _TRACING_ENABLED
    _TRACING_ENABLED = True
    
    logger.info("Tracing is enabled.")


def disable_tracing() -> None:
    """Disable the global tracing toggle. 
    All `comment_*` calls become no-ops and pure comments."""
    global _TRACING_ENABLED
    _TRACING_ENABLED = False

    logger.info("Tracing is disabled.")


def is_tracing_enabled() -> bool:
    """Return whether tracing is currently enabled."""
    return _TRACING_ENABLED


def current_graph() -> ExecNetwork | None:
    """Return the active execution graph, if any."""
    return _GRAPH.get()


def current_session() -> Session | None:
    """Return the active session, if any."""
    return _SESSION.get()


def current_op() -> OpRecord | None:
    """Return the active operation record, if any."""
    return _OP.get()


def current_context() -> TracingContext | None:
    """Return the active tracing context, if any."""
    return _TRACING_CTX.get()


@contextmanager
def comment_graph(
    *,
    graph_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    storage_path: str | None = None,
    driver_type: str | None = None,
    graph: ExecNetwork | None = None,
    metadata: dict[str, JsonValue] | None = None,
    strict: bool | None = None,
) -> Iterator[ExecNetwork | None]:
    """Create or adopt an execution network and set it as the active graph.

    Args:
        graph_id (`str | None`, optional):
            Explicit graph identifier. It is automatically generated if omitted.
        user_id (`str | None`, optional):
            User identifier that owns the graph.
        project_id (`str | None`, optional):
            Project identifier that owns the graph.
        storage_path (`str | None`, optional):
            On-disk path for persistent storage.
        driver_type (`str | None`, optional):
            Registered driver backend name. It defaults to ``"in_memory"`` 
            when creating a new graph.
        graph (`ExecNetwork | None`, optional):
            An existing graph to continue.
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata merged into the graph.
        strict (`bool | None`, optional):
            Enable or disable strict consistency checking for this
            graph.  When it is enabled, encountering a changed value for
            an existing identity without an explicit ``comment_mutation`` raises
            a trace consistency error. It defaults to ``False``.  When an existing
            graph is passed in, this parameter overrides its current setting
            only if explicitly provided.

    Yields:
        `ExecNetwork | None`:
            The active graph if tracing is enabled.
    """
    if not _TRACING_ENABLED:
        yield None
        return

    created = False
    if graph is None:
        kwargs = {}
        if graph_id is not None:
            kwargs["graph_id"] = graph_id
        if user_id is not None:
            kwargs["user_id"] = user_id
        if project_id is not None:
            kwargs["project_id"] = project_id
        if storage_path is not None:
            kwargs["storage_path"] = storage_path
        if driver_type is not None:
            kwargs["driver_type"] = driver_type
        if strict is not None:
            kwargs["strict"] = strict
        graph = ExecNetwork(**kwargs)
        created = True
    elif strict is not None:
        graph.strict = strict

    if metadata:
        graph.update_metadata(metadata)

    # Set up tracing context and inherit propagated attributes.
    ctx = TracingContext()
    parent_ctx = _TRACING_CTX.get()
    if parent_ctx is not None:
        ctx._runtime_variables = parent_ctx._runtime_variables.copy()
        ctx._full_node_id_to_names = {
            fid: names.copy()
            for fid, names in parent_ctx._full_node_id_to_names.items()
        }
        ctx.update_metadata(parent_ctx.metadata)
        # Inject propagated attributes onto the graph schema object.
        if parent_ctx.metadata:
            graph.update_metadata(parent_ctx.metadata)

    if created:
        logger.info(
            "An execution graph (graph_id={}, driver_type={}, strict={}) is created.",
            graph.graph_id,
            graph.driver_type,
            graph.strict,
        )
    else:
        logger.debug(
            "An existing execution graph (graph_id={}) is adopted.",
            graph.graph_id,
        )

    token_graph = _GRAPH.set(graph)
    token_ctx = _TRACING_CTX.set(ctx)
    try:
        yield graph
    finally:
        _GRAPH.reset(token_graph)
        _TRACING_CTX.reset(token_ctx)


@contextmanager
def comment_session(
    *,
    session_id: str | None = None,
    session_name: str | None = None,
    comment: str | None = None,
    category: str = "session",
    metadata: dict[str, JsonValue] | None = None,
) -> Iterator[RuntimeSession | None]:
    """Create a session and set it as the active session.

    Args:
        session_id (`str | None`, optional):
            Explicit session identifier.
        session_name (`str | None`, optional):
            Human-readable session name.
        comment (`str | None`, optional):
            Session description.
        category (`str`, defaults to `"session"`):
            Session category.
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata for the session schema object.

    Yields:
        `RuntimeSession | None`:
            A read-only session handle if tracing is enabled.

    Raises:
        `RuntimeError`:
            If no graph context is active and tracing is enabled.
        `ValueError`:
            If provided session identifier is the reserved NONE sentinel session identifier.
    """
    if not _TRACING_ENABLED:
        yield None
        return

    graph = _GRAPH.get()
    if graph is None:
        raise RuntimeError(
            "`comment_session` requires an active graph context. "
            "Wrap your code in `with comment_graph() as graph:`."
        )
    none_sid = none_session_id()
    if session_id == none_sid:
        raise ValueError(
            f"The session identifier '{none_sid}' is reserved for the built-in "
            "NONE sentinel."
        )

    frame = inspect.stack()[2]
    kwargs = {
        "graph_id": graph.graph_id,
        "user_id": graph.user_id,
        "project_id": graph.project_id,
        "category": category,
        "filename": frame.filename,
        "lineno": frame.lineno,
    }
    if session_id is not None:
        kwargs["session_id"] = session_id
    if session_name is not None:
        kwargs["session_name"] = session_name
    if comment is not None:
        kwargs["comment"] = comment

    session = Session(**kwargs)
    if metadata:
        session.update_metadata(metadata)

    # Inject propagated attributes onto the session schema.
    parent_ctx = _TRACING_CTX.get()
    assert parent_ctx is not None, (
        "The tracing context must be active when `comment_session` is called."
    )
    propagated = parent_ctx.metadata
    if propagated:
        session.update_metadata(propagated)

    # Persist the session in the graph driver.
    graph._driver.add_session(session)

    # Set up tracing context and inherit propagated attributes.
    ctx = TracingContext()
    ctx._runtime_variables = parent_ctx._runtime_variables.copy()
    ctx._full_node_id_to_names = {
        fid: names.copy()
        for fid, names in parent_ctx._full_node_id_to_names.items()
    }
    ctx.update_metadata(parent_ctx.metadata)

    token_session = _SESSION.set(session)
    token_ctx = _TRACING_CTX.set(ctx)
    try:
        yield RuntimeSession(session=session)
    finally:
        _SESSION.reset(token_session)
        _TRACING_CTX.reset(token_ctx)


@contextmanager
def comment_op_scope(
    *,
    op_name: str | None = None,
    comment: str | None = None,
    category: str = "operation",
    metadata: dict[str, JsonValue] | None = None,
) -> Iterator[RuntimeOp | None]:
    """Create an operation record scope and set it as the active operation.

    If no session is active, an anonymous session is created automatically 
    for the duration of this scope.
    
    Args:
        op_name (`str | None`, optional):
            Operation name.
        comment (`str | None`, optional):
            Operation description.
        category (`str`, defaults to `"operation"`):
            Operation category.
        metadata (`dict[str, JsonValue] | None`, optional):
            Extra metadata.

    Yields:
        `RuntimeOp | None`:
            A read-only operation handle if tracing is enabled.

    Raises:
        `RuntimeError`:
            If no graph context is active and tracing is enabled.
    """
    if not _TRACING_ENABLED:
        yield None
        return

    graph = _GRAPH.get()
    if graph is None:
        raise RuntimeError(
            "`comment_op_scope` requires an active graph context. "
            "Wrap your code in `with comment_graph() as graph:`."
        )

    tracing_ctx = _TRACING_CTX.get()
    assert tracing_ctx is not None, (
        "The tracing context must be active when `comment_op_scope` is called."
    )

    session = _SESSION.get()
    auto_session_token = None
    if session is None:
        frame_session = inspect.stack()[2]
        session = Session(
            graph_id=graph.graph_id,
            user_id=graph.user_id,
            project_id=graph.project_id,
            category="session",
            filename=frame_session.filename,
            lineno=frame_session.lineno,
        )
        if tracing_ctx.metadata:
            session.update_metadata(tracing_ctx.metadata)
        graph._driver.add_session(session)
        auto_session_token = _SESSION.set(session)

    frame = inspect.stack()[2]
    op = OpRecord(
        graph_id=graph.graph_id,
        session_id=session.session_id,
        user_id=graph.user_id,
        project_id=graph.project_id,
        op_name=op_name,
        comment=comment,
        category=category,
        filename=frame.filename,
        lineno=frame.lineno,
    )
    if metadata:
        op.update_metadata(metadata)

    propagated = tracing_ctx.metadata
    if propagated:
        op.update_metadata(propagated)

    # Persist the operation in the graph driver.
    graph._driver.add_operation(op)

    token_op = _OP.set(op)
    try:
        yield RuntimeOp(op=op)
    finally:
        _OP.reset(token_op)
        if auto_session_token is not None:
            _SESSION.reset(auto_session_token)


@contextmanager
def propagate_attributes(
    **attrs: Any,
) -> Iterator[None]:
    """Add key-value attributes to the tracing context for propagation.

    Attributes set here flow through the context inheritance chain and
    are automatically injected into every execution network, session,
    operation record, and variable created in nested scopes.

    Example::

        with propagate_attributes(run_id="exp-1", model="gpt-4"):
            with comment_graph() as graph:
                # `graph.metadata` contains `run_id` and `model`. 
                with comment_session(session_name="s1"):
                    rv = comment_variable("hello", id_strategy="content")
                    # `rv.metadata` also contains `run_id` and `model`. 

    Args:
        **attrs (`Any`):
            Arbitrary key-value pairs to propagate.
    """
    if not _TRACING_ENABLED:
        yield
        return

    parent_ctx = _TRACING_CTX.get()

    ctx = TracingContext()
    if parent_ctx is not None:
        ctx._runtime_variables = parent_ctx._runtime_variables.copy()
        ctx._full_node_id_to_names = {
            fid: names.copy()
            for fid, names in parent_ctx._full_node_id_to_names.items()
        }
        ctx.update_metadata(parent_ctx.metadata)
    ctx.update_metadata(attrs)

    token = _TRACING_CTX.set(ctx)
    try:
        yield
    finally:
        _TRACING_CTX.reset(token)
