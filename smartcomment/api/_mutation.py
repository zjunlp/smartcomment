from pydantic import BaseModel, JsonValue
from ..schema.variable import Variable
from ..schema.operation import OpRecord, OpEdge
from ..runtime import (
    current_context,
    current_op,
    is_tracing_enabled,
)
from ..runtime.variable import RuntimeVariable
from ._helpers import (
    _resolve_call_context,
    _ensure_variable,
    _resolve_item,
)
from types import TracebackType
from typing import (
    Any, 
    Callable, 
    Generic, 
    Self,
    TypeVar,
) 


T = TypeVar("T")


class _MutationScope(Generic[T]):
    """Context manager that records an in-place mutation as a new variable version.

    Instances are created by :func:`comment_mutation` and should not be
    instantiated directly.  On entry, the current value of target is
    snapshotted. On exit, the target is re-encoded and a new version node,
    an operation record, and connecting edges are written to the execution graph.
    """

    __slots__ = (
        "_target", "_inputs", 
        "_comment", "_category", "_class_name", "_auto_class_name", 
        "_id_strategy", "_encoding_fn", "_decoding_fn", "_schema", 
        "_mutation_name", "_mutation_comment", "_mutation_category",
        "_metadata", "_mutation_metadata", "_reuse_op",
        "_result", 
        "_before_rv", "_graph", "_session_id", "_filename", "_lineno", "_input_rvs", 
        "_tracing_active",
    )

    def __init__(
        self,
        *,
        target: T,
        inputs: list[Any] | None,
        comment: str | None,
        category: str,
        class_name: str | None,
        auto_class_name: bool,
        id_strategy: Callable[[Any], str] | str | None,
        encoding_fn: Callable[[Any], str] | None,
        decoding_fn: Callable[[str], Any] | None,
        schema: type[BaseModel] | None,
        mutation_name: str | None,
        mutation_comment: str | None,
        mutation_category: str,
        metadata: dict[str, JsonValue] | None,
        mutation_metadata: dict[str, JsonValue] | None,
        reuse_op: bool = False,
    ) -> None:
        self._target = target
        self._inputs = inputs
        self._comment = comment
        self._category = category
        self._class_name = class_name
        self._auto_class_name = auto_class_name
        self._id_strategy = id_strategy
        self._encoding_fn = encoding_fn
        self._decoding_fn = decoding_fn
        self._schema = schema
        self._mutation_name = mutation_name
        self._mutation_comment = mutation_comment
        self._mutation_category = mutation_category
        self._metadata = metadata
        self._mutation_metadata = mutation_metadata
        self._reuse_op = reuse_op
        self._result = None
        self._before_rv = None
        self._graph = None
        self._session_id = None
        self._filename = None
        self._lineno = None
        self._input_rvs = []

        # It denotes whether this scope is currently active.
        self._tracing_active = False

    @property
    def target(self) -> T:
        """The mutable Python object being tracked."""
        return self._target

    @property
    def result(self) -> RuntimeVariable[T] | None:
        """The runtime variable for the new version, available after exit.

        It returns ``None`` when tracing is disabled or the `with` block
        has not yet exited.
        """
        return self._result

    def __enter__(self) -> Self:
        if not is_tracing_enabled():
            return self

        # Mark this scope as active.
        self._tracing_active = True

        graph, session_id, filename, lineno = _resolve_call_context(
            caller_name="comment_mutation",
        )
        self._graph = graph
        self._session_id = session_id
        self._filename = filename
        self._lineno = lineno

        # Get the runtime variable for the before-mutation state.
        self._before_rv = _ensure_variable(
            self._target,
            id_strategy=self._id_strategy,
            encoding_fn=self._encoding_fn,
            decoding_fn=self._decoding_fn,
            schema=self._schema,
            comment=self._comment,
            category=self._category,
            class_name=self._class_name,
            auto_class_name=self._auto_class_name,
            metadata=self._metadata,
            graph=graph,
            session_id=session_id,
            filename=filename,
            lineno=lineno,
            force_new_version=False,
        )

        if self._inputs:
            resolve_kwargs = dict(
                shared_id_strategy=self._id_strategy,
                shared_encoding_fn=self._encoding_fn,
                shared_decoding_fn=self._decoding_fn,
                shared_schema=self._schema,
                shared_auto_class_name=self._auto_class_name,
                shared_category=self._category,
                shared_metadata=self._metadata,
                graph=graph,
                session_id=session_id,
                filename=filename,
                lineno=lineno,
            )
            self._input_rvs = [
                _resolve_item(item, **resolve_kwargs)
                for item in self._inputs
            ]
            target_fid = self._before_rv.full_node_id
            for rv in self._input_rvs:
                if rv.full_node_id == target_fid:
                    raise ValueError(
                        "An input variable with the full node identifier "
                        f"'{rv.full_node_id}' collides with the mutation "
                        "target.  Self-referencing inputs are not allowed."
                    )

        return self

    # noinspection PyUnusedLocal
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        # Return `False` to propagate any exception that occurred in the with-block.
        if exc_type is not None or not self._tracing_active:
            return False

        graph = self._graph
        session_id = self._session_id
        filename = self._filename
        lineno = self._lineno
        before_rv = self._before_rv

        # Re-encode the (now-mutated) target variable.
        if self._schema is not None and self._encoding_fn is None:
            after_value_str = self._target.model_dump_json()
        elif self._encoding_fn is not None:
            after_value_str = self._encoding_fn(self._target)
        else:
            after_value_str = repr(self._target)

        new_var = Variable(
            name=before_rv.name,
            version=before_rv.version + 1,
            value=after_value_str,
            comment=before_rv.comment,
            category=before_rv.category,
            class_name=before_rv.class_name,
            graph_id=graph.graph_id,
            user_id=graph.user_id,
            project_id=graph.project_id,
            session_id=session_id,
            filename=filename,
            lineno=lineno,
        )
        if self._metadata:
            new_var.update_metadata(self._metadata)

        ctx = current_context()

        assert ctx is not None, (
            "The current tracing context is not active."
        )

        propagated = ctx.metadata
        if propagated:
            new_var.update_metadata(propagated)

        graph._driver.add_node(new_var)
        new_full_node_id = new_var.full_node_id

        active_op = current_op() if self._reuse_op else None
        if active_op is not None:
            op = active_op
        else:
            mutation_name = self._mutation_name or f"mutation:{before_rv.full_name}"
            op = OpRecord(
                graph_id=graph.graph_id,
                session_id=session_id,
                user_id=graph.user_id,
                project_id=graph.project_id,
                op_name=mutation_name,
                comment=self._mutation_comment,
                category=self._mutation_category,
                filename=filename,
                lineno=lineno,
            )
            if self._mutation_metadata:
                op.update_metadata(self._mutation_metadata)
            if propagated:
                op.update_metadata(propagated)
            graph._driver.add_operation(op)

        # Edges receive the operation metadata.
        edge_metadata = {}
        if self._mutation_metadata:
            edge_metadata.update(self._mutation_metadata)
        if propagated:
            edge_metadata.update(propagated)

        # Version edge generated by in-place mutation.
        # If the user provide the comment on this in-place mutation
        # it will be used for the version edge.
        # Otherwise, the default comment `"Version lineage."` will be used.
        edge_comment = self._mutation_comment or "Version lineage."
        version_edge = OpEdge(
            graph_id=graph.graph_id,
            session_id=session_id,
            user_id=graph.user_id,
            project_id=graph.project_id,
            op_id=op.op_id,
            category=self._mutation_category,
            source_full_node_id=before_rv.full_node_id,
            target_full_node_id=new_full_node_id,
            comment=edge_comment,
            filename=filename,
            lineno=lineno,
        )
        if edge_metadata:
            version_edge.update_metadata(edge_metadata)
        graph._driver.add_edge(version_edge)

        # Input edges inherit the operation's category and comment.
        for input_rv in self._input_rvs:
            edge = OpEdge(
                graph_id=graph.graph_id,
                session_id=session_id,
                user_id=graph.user_id,
                project_id=graph.project_id,
                op_id=op.op_id,
                category=self._mutation_category,
                source_full_node_id=input_rv.full_node_id,
                target_full_node_id=new_full_node_id,
                comment=self._mutation_comment,
                filename=filename,
                lineno=lineno,
            )
            if edge_metadata:
                edge.update_metadata(edge_metadata)
            graph._driver.add_edge(edge)

        # Create the runtime variable for the new version.
        # The user can access this runtime variable after the `with` block exits.
        self._result = RuntimeVariable(
            variable=new_var,
            encoding_fn=self._encoding_fn,
            decoding_fn=self._decoding_fn,
            schema=self._schema,
        )
        return False

    def __repr__(self) -> str:
        """Get the string representation of the mutation scope."""
        if self._result is None:
            return (
                f"{self.__class__.__name__}(target={self._target!r}, "
                f"tracing_active={self._tracing_active})"
            )
        return (
            f"{self.__class__.__name__}(target={self._target!r}, "
            f"tracing_active={self._tracing_active}, "
            f"result={self._result!r})"
        )