"""The top-level execution graph."""

import re
import copy
from uuid import uuid4
from pydantic import (
    Field,
    ModelWrapValidatorHandler,
    PrivateAttr,
    model_serializer,
    model_validator,
    SerializerFunctionWrapHandler, 
)
from .graph import RuntimeGraph
from .operation import RuntimeEdge, RuntimeOp
from .errors import ExecNetworkKeyError
from .session import RuntimeSession
from .variable import RuntimeVariable
from ..analysis.visualization import _VISUAL_BACKENDS
from ..schema.base import BaseMetadataModel, _get_timestamp
from ..schema.operation import OpEdge, OpRecord
from ..schema.session import Session
from ..schema.variable import Variable
from ..drivers import _DRIVER_BACKENDS
from ..drivers.base import GraphDriver
from typing import (
    Any,
    Literal,
    Self, 
    Iterable, 
)


_NONE_IDENTITY = "COMMENT:NONE"
_NONE_SESSION_ID = "__none__"
_NONE_OP_ID = "__none_op__"


def none_identity() -> str:
    """Return the reserved identity string for the NONE sentinel.

    Returns:
        `str`:
            The sentinel identity.
    """
    return _NONE_IDENTITY


def none_full_node_id() -> str:
    """Return the full node identifier of the NONE sentinel.

    Returns:
        `str`:
            The sentinel full node identifier.
    """
    return f"{_NONE_IDENTITY}@1"


def none_session_id() -> str:
    """Return the reserved session identifier used by NONE sentinels.

    Returns:
        `str`:
            The sentinel session identifier.
    """
    return _NONE_SESSION_ID


def none_op_id() -> str:
    """Return the reserved operation identifier used by NONE sentinels.

    Returns:
        `str`:
            The sentinel operation identifier.
    """
    return _NONE_OP_ID


class ExecNetwork(BaseMetadataModel):
    """Top-level execution graph that owns a graph driver."""

    graph_id: str = Field(
        default_factory=lambda: f"graph-{uuid4().hex}",
        description="Unique graph identifier.",
    )
    user_id: str | None = Field(
        default=None,
        description="User that owns this graph.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project this graph belongs to.",
    )
    storage_path: str | None = Field(
        default=None,
        description="Optional on-disk path used by persistent drivers.",
    )
    strict: bool = Field(
        default=False,
        description=(
            "When it is enabled, encountering a changed value for an existing "
            "identity without an explicit `comment_mutation` raises a "
            "trace consistency error."
        ),
    )
    driver_type: str = Field(
        default="in_memory",
        description=(
            "Built-in storage backend name."
        ),
    )
    created_at: str = Field(
        default_factory=_get_timestamp,
        description="Creation timestamp.",
    )

    _driver: GraphDriver | None = PrivateAttr(default=None)


    @model_validator(mode="wrap")
    @classmethod
    def _extract_and_restore(
        cls,
        values: Any,
        handler: ModelWrapValidatorHandler[Self],
    ) -> Self:
        """Extract graph data from serialized input and resolve the driver.

        Args: 
            values (`Any`):
                The input values to validate.
            handler (`ModelWrapValidatorHandler[Self]`):
                The handler function to create the instance.

        Returns:
            `Self`:
                The validated instance.
        """
        graph_data = {}
        if isinstance(values, dict):
            graph_data = values.pop("data", {})

        instance = handler(values)

        if instance.driver_type not in _DRIVER_BACKENDS:
            raise ValueError(
                f"'{instance.driver_type}' is not a supported driver backend. "
                "Available driver backends " 
                f"are {', '.join(list(_DRIVER_BACKENDS.keys()))}."
            )
            
        driver_cls = _DRIVER_BACKENDS[instance.driver_type]
        if graph_data:
            # Restore the driver from the serialized graph data if it is provided.
            instance._driver = driver_cls.deserialize(graph_data)
        else: 
            # Otherwise, we create a fresh driver.
            instance._driver = driver_cls()
        return instance

    @model_serializer(mode="wrap")
    def _serialize_with_graph_data(
        self, 
        handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        """Include live graph data under the ``data`` key during serialization.

        Args:
            handler (`SerializerFunctionWrapHandler`):
                The handler function to serialize the instance.

        Returns:
            `dict[str, Any]`:
                The serialized instance.
        """
        # Serialize the instance.
        d = handler(self)
        if self._driver is not None:
            d["data"] = self._driver.serialize()
        return d

    def contributing_sessions(self, full_node_id: str) -> list[RuntimeSession]:
        """Return sessions for the start node and every upstream ancestor.

        It walks incoming edges (upstream BFS closure), collects unique session
        identifiers from the traversed nodes, looks each one up in the driver,
        and returns them deduplicated and sorted by their creation time ascending.

        Args:
            full_node_id (`str`):
                Full node identifier to trace from.

        Returns:
            `list[RuntimeSession]`:
                Distinct sessions on nodes in the upstream closure, sorted by
                creation time from earliest to latest.
        """
        seen_ids = set()
        sessions = []
        for nid in self._reachable_closure(full_node_id, direction="incoming"):
            node = self._driver.get_node(nid)
            assert node is not None, (
                f"A dangling full node identifier '{nid}' is found in the graph. "
                "The graph may be damaged." 
            )
            if node.session_id not in seen_ids:
                seen_ids.add(node.session_id)
                session = self._driver.get_session(node.session_id)
                assert session is not None, (
                    f"A dangling session identifier '{node.session_id}' is found "
                    f"on the variable '{node.full_node_id}'. The graph may be damaged."
                )
                sessions.append(session)

        sessions.sort(key=lambda s: s.created_at)
        return [RuntimeSession(session=s) for s in sessions]

    def get_ancestors(
        self,
        full_node_id: str,
        max_depth: int | None = None,
    ) -> list[RuntimeVariable[Any]]:
        """Return upstream ancestor nodes reachable via incoming edges.

        Args:
            full_node_id (`str`):
                Starting full node identifier.
            max_depth (`int | None`, optional):
                Maximum number of hops from the starting node.  When not
                provided, all reachable ancestors are returned.  ``1``
                returns direct parents only, ``2`` includes grandparents,
                and so on.

        Returns:
            `list[RuntimeVariable[Any]]`:
                Ancestor nodes sorted by creation time from earliest to latest.
        """
        closure = self._reachable_closure(
            full_node_id, 
            direction="incoming", 
            max_depth=max_depth,
        )
        closure.discard(full_node_id)
        nodes = []
        for nid in closure:
            node = self._driver.get_node(nid)
            assert node is not None, (
                f"A dangling full node identifier '{nid}' is found in the graph. "
                "The graph may be damaged." 
            )
            nodes.append(node)

        nodes.sort(key=lambda v: v.created_at)
        return [RuntimeVariable(variable=v) for v in nodes]

    def get_descendants(
        self,
        full_node_id: str,
        max_depth: int | None = None,
    ) -> list[RuntimeVariable[Any]]:
        """Return downstream descendant nodes reachable via outgoing edges.

        Args:
            full_node_id (`str`):
                Starting full node identifier.
            max_depth (`int | None`, optional):
                Maximum number of hops from the starting node.  When not
                provided, all reachable descendants are returned.  ``1``
                returns direct children only, ``2`` includes grandchildren,
                and so on.

        Returns:
            `list[RuntimeVariable[Any]]`:
                Descendant nodes sorted by creation time from earliest to latest.
        """
        closure = self._reachable_closure(
            full_node_id, 
            direction="outgoing", 
            max_depth=max_depth,
        )
        closure.discard(full_node_id)
        nodes = []
        for nid in closure:
            node = self._driver.get_node(nid)
            assert node is not None, (
                f"A dangling full node identifier '{nid}' is found in the graph. "
                "The graph may be damaged." 
            )
            nodes.append(node)

        nodes.sort(key=lambda v: v.created_at)
        return [RuntimeVariable(variable=v) for v in nodes]

    def get_downstream_sessions(self, full_node_id: str) -> list[RuntimeSession]:
        """Return sessions for the start node and every downstream descendant.

        It walks outgoing edges (downstream BFS closure), collects unique session
        identifiers from the traversed nodes, looks each one up in the driver,
        and returns them deduplicated and sorted by their creation time ascending.

        Args:
            full_node_id (`str`):
                Full node identifier to trace from.

        Returns:
            `list[RuntimeSession]`:
                Distinct sessions on nodes in the downstream closure, sorted by
                creation time from earliest to latest.
        """
        seen_ids = set()
        sessions = []
        for nid in self._reachable_closure(full_node_id, direction="outgoing"):
            node = self._driver.get_node(nid)
            assert node is not None, (
                f"A dangling full node identifier '{nid}' is found in the graph. "
                "The graph may be damaged." 
            )
            if node.session_id not in seen_ids:
                seen_ids.add(node.session_id)
                session = self._driver.get_session(node.session_id)
                assert session is not None, (
                    f"A dangling session identifier '{node.session_id}' is found "
                    f"on the variable '{node.full_node_id}'. The graph may be damaged."
                )
                sessions.append(session)

        sessions.sort(key=lambda s: s.created_at)
        return [RuntimeSession(session=s) for s in sessions]

    def __contains__(self, full_node_id: str) -> bool:
        """Check whether a node with the given full node identifier exists.

        Args:
            full_node_id (`str`):
                The full node identifier to check.

        Returns:
            `bool`:
                ``True`` if the node exists in the graph.
        """
        return self._driver.has_node(full_node_id)

    def _ensure_none_session(self) -> None:
        """Lazily create the per-graph NONE sentinel session.

        The session is created only on first need. Multiple callers
        without an active session can safely call this, and the session 
        is inserted at most once.
        """
        sid = none_session_id()
        if self._driver.get_session(sid) is None:
            self._driver.add_session(
                Session(
                    session_id=sid,
                    session_name="NONE sentinel",
                    graph_id=self.graph_id,
                    user_id=self.user_id,
                    project_id=self.project_id,
                    category="sentinel",
                    filename="<sentinel>",
                    lineno=0,
                )
            )

    def _ensure_none_node(self) -> None:
        """Lazily create the per-graph NONE sentinel variable.

        The node is created only on first need. If the user never records an
        operation with no inputs or no outputs, the sentinel is never inserted
        and does not appear in the graph or in export data.
        """
        sentinel_id = none_full_node_id()
        if sentinel_id in self:
            return

        self._ensure_none_session()

        none_name = none_identity()
        none_var = Variable(
            name=none_name,
            version=1,
            value="NONE",
            category="sentinel",
            graph_id=self.graph_id,
            user_id=self.user_id,
            project_id=self.project_id,
            session_id=none_session_id(),
            filename="<sentinel>",
            lineno=0,
        )
        self._driver.add_node(none_var)

    def _ensure_none_op(self) -> None:
        """Lazily create the per-graph NONE sentinel operation.

        The operation is created only on first need. If the user never creates an
        edge with no active operation scope, the sentinel is never inserted
        and does not appear in the graph or in export data.
        """
        nop_id = none_op_id()
        if self._driver.get_operation(nop_id) is not None:
            return

        self._ensure_none_session()

        op = OpRecord(
            op_id=nop_id,
            graph_id=self.graph_id,
            session_id=none_session_id(),
            user_id=self.user_id,
            project_id=self.project_id,
            op_name="NONE sentinel",
            category="sentinel",
            comment=None,
            filename="<sentinel>",
            lineno=0,
        )
        self._driver.add_operation(op)

    def add_variable(self, variable: RuntimeVariable[Any]) -> None:
        """Add a variable to the graph via its runtime handle.

        Args:
            variable (`RuntimeVariable[Any]`):
                The runtime variable whose underlying schema node will
                be inserted into the driver.

        Raises:
            `TypeError`:
                If the variable is not a runtime variable.
            `ValueError`:
                If the variable uses the reserved NONE identity.
        """
        if not isinstance(variable, RuntimeVariable):
            raise TypeError(
                "A runtime variable is expected " 
                f"but an instance of '{type(variable).__name__}' is provided."
            )

        none_name = none_identity()
        if variable.name == none_name:
            raise ValueError(
                f"The identity '{none_name}' is reserved for the built-in NONE sentinel."
            )

        raw = variable._variable
        stored = raw.model_copy(
            deep=True,
            update={
                "graph_id": self.graph_id,
                "user_id": self.user_id,
                "project_id": self.project_id,
            },
        )
        stored._metadata = copy.deepcopy(raw._metadata)
        self._driver.add_node(stored)

    def remove_variable(self, full_node_id: str) -> None:
        """Remove a variable node from the graph.

        Args:
            full_node_id (`str`):
                The full node identifier of the variable to remove.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        node = self._driver.get_node(full_node_id)
        if node is None:
            raise ExecNetworkKeyError(
                f"The variable '{full_node_id}' is not found in the graph."
            )

        self._driver.remove_node(full_node_id)

    def add_edge(self, edge: RuntimeEdge) -> None:
        """Add an edge to the graph via its runtime handle.

        Args:
            edge (`RuntimeEdge`):
                The runtime edge whose underlying schema edge will
                be inserted into the driver.

        Raises:
            `TypeError`:
                If the edge is not a runtime edge.
        """
        if not isinstance(edge, RuntimeEdge):
            raise TypeError(
                "A runtime edge is expected " 
                f"but an instance of '{type(edge).__name__}' is provided."
            )

        raw = edge._edge
        stored = raw.model_copy(
            deep=True,
            update={
                "graph_id": self.graph_id,
                "user_id": self.user_id,
                "project_id": self.project_id,
            },
        )
        raw._metadata = copy.deepcopy(raw._metadata)
        self._driver.add_edge(stored)

    def add_operation(self, op: RuntimeOp) -> None:
        """Add an operation to the graph via its runtime handle.

        Args:
            op (`RuntimeOp`):
                The runtime operation whose underlying schema record
                will be inserted into the driver.

        Raises:
            `TypeError`:
                If the operation is not a runtime operation.
            `ValueError`:
                If the operation uses the reserved NONE sentinel operation identifier.
        """
        if not isinstance(op, RuntimeOp):
            raise TypeError(
                "A runtime operation is expected " 
                f"but an instance of '{type(op).__name__}' is provided."
            )

        raw = op._op
        nop_id = none_op_id()
        if raw.op_id == nop_id:
            raise ValueError(
                f"The operation identifier '{nop_id}' is reserved for the "
                "built-in NONE sentinel."
            )

        stored = raw.model_copy(
            deep=True,
            update={
                "graph_id": self.graph_id,
                "user_id": self.user_id,
                "project_id": self.project_id,
            },
        )
        raw._metadata = copy.deepcopy(raw._metadata)
        self._driver.add_operation(stored)

    def remove_operation(self, op_id: str) -> None:
        """Remove an operation and cascade-delete its edges.

        Args:
            op_id (`str`):
                The operation identifier to remove.

        Raises:
            `ExecNetworkKeyError`:
                If the operation is not found in the graph.
        """
        op = self._driver.get_operation(op_id)
        if op is None:
            raise ExecNetworkKeyError(
                f"The operation '{op_id}' is not found in the graph."
            )

        self._driver.remove_operation(op_id)

    def remove_edge(self, edge_id: str) -> None:
        """Remove an edge from the graph.

        Args:
            edge_id (`str`):
                The edge identifier to remove.

        Raises:
            `ExecNetworkKeyError`:
                If the edge is not found in the graph.
        """
        edge = self._driver.get_edge(edge_id)
        if edge is None:
            raise ExecNetworkKeyError(
                f"The edge '{edge_id}' is not found in the graph."
            )

        self._driver.remove_edge(edge_id)

    def add_session(self, session: RuntimeSession) -> None:
        """Add a session to the graph via its runtime handle.

        Args:
            session (`RuntimeSession`):
                The runtime session whose underlying schema will be
                inserted into the driver.

        Raises:
            `TypeError`:
                If the session is not a runtime session.
            `ValueError`:
                If the session uses the reserved NONE sentinel session identifier.
        """
        if not isinstance(session, RuntimeSession):
            raise TypeError(
                "A runtime session is expected "
                f"but an instance of '{type(session).__name__}' is provided."
            )

        raw = session._session
        sid = none_session_id()
        if raw.session_id == sid:
            raise ValueError(
                f"The session identifier '{sid}' is reserved for the built-in "
                "NONE sentinel."
            )

        stored = raw.model_copy(
            deep=True,
            update={
                "graph_id": self.graph_id,
                "user_id": self.user_id,
                "project_id": self.project_id,
            },
        )
        stored._metadata = copy.deepcopy(raw._metadata)
        self._driver.add_session(stored)

    def remove_session(self, session_id: str) -> None:
        """Remove a session and cascade-delete its operations, nodes, and edges.

        Args:
            session_id (`str`):
                The session identifier to remove.

        Raises:
            `ExecNetworkKeyError`:
                If the session is not found in the graph.
        """
        session = self._driver.get_session(session_id)
        if session is None:
            raise ExecNetworkKeyError(
                f"The session '{session_id}' is not found in the graph."
            )

        self._driver.remove_session(session_id)

    def get_session(self, session_id: str) -> RuntimeSession:
        """Retrieve a session by its identifier.

        Args:
            session_id (`str`):
                The session identifier to look up.

        Returns:
            `RuntimeSession`:
                The runtime session handle.

        Raises:
            `ExecNetworkKeyError`:
                If the session is not found in the graph.
        """
        session = self._driver.get_session(session_id)
        if session is None:
            raise ExecNetworkKeyError(
                f"The session '{session_id}' is not found in the graph."
            )
        return RuntimeSession(session=session)

    def get_variable(self, full_node_id: str) -> RuntimeVariable[Any]:
        """Retrieve a variable by its full node identifier.

        Args:
            full_node_id (`str`):
                The full node identifier to look up.

        Returns:
            `RuntimeVariable[Any]`:
                The runtime variable handle.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        node = self._driver.get_node(full_node_id)
        if node is None:
            raise ExecNetworkKeyError(
                f"The variable '{full_node_id}' is not found in the graph."
            )
        return RuntimeVariable(variable=node)

    def get_operation(self, op_id: str) -> RuntimeOp:
        """Retrieve an operation by its identifier.

        Args:
            op_id (`str`):
                The operation identifier to look up.

        Returns:
            `RuntimeOp`:
                The runtime operation handle.

        Raises:
            `ExecNetworkKeyError`:
                If the operation is not found in the graph.
        """
        op = self._driver.get_operation(op_id)
        if op is None:
            raise ExecNetworkKeyError(
                f"The operation '{op_id}' is not found in the graph."
            )
        return RuntimeOp(op=op)

    def get_edge(self, edge_id: str) -> RuntimeEdge:
        """Retrieve an edge by its identifier.

        Args:
            edge_id (`str`):
                The edge identifier to look up.

        Returns:
            `RuntimeEdge`:
                The runtime edge handle.

        Raises:
            `ExecNetworkKeyError`:
                If the edge is not found in the graph.
        """
        edge = self._driver.get_edge(edge_id)
        if edge is None:
            raise ExecNetworkKeyError(
                f"The edge '{edge_id}' is not found in the graph."
            )
        return RuntimeEdge(edge=edge)

    def get_operations_by_variable(self, full_node_id: str) -> list[RuntimeOp]:
        """Return operations that directly involve a variable node.

        Args:
            full_node_id (`str`):
                The full node identifier to query.

        Returns:
            `list[RuntimeOp]`:
                Distinct operations connected to the variable, sorted by
                creation time ascending.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        if full_node_id not in self:
            raise ExecNetworkKeyError(
                f"The variable '{full_node_id}' is not found in the graph."
            )

        op_ids = {
            edge.op_id
            for direction in ("incoming", "outgoing")
            for edge in self._driver.get_edges_by_node(full_node_id, direction=direction)
        }
        ops = []
        for op_id in op_ids:
            op = self._driver.get_operation(op_id)
            assert op is not None, (
                f"A dangling operation identifier '{op_id}' is found "
                f"on edges connected to variable '{full_node_id}'. "
                "The graph may be damaged."
            )
            ops.append(op)

        ops.sort(key=lambda o: o.created_at)
        return [RuntimeOp(op=o) for o in ops]

    def get_all_sessions(self) -> list[RuntimeSession]:
        """Return all sessions wrapped as runtime handles.

        Returns:
            `list[RuntimeSession]`:
                Every session in the graph.
        """
        return [RuntimeSession(session=s) for s in self._driver.all_sessions()]

    def filter_by_session(
        self,
        session_id: str | Iterable[str],
    ) -> RuntimeGraph:
        """Return a subgraph of variables belonging to the given session(s).

        Args:
            session_id (`str | Iterable[str]`):
                A single session identifier or an iterable of session
                identifiers. 

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view.
        """
        sids = {session_id} if isinstance(session_id, str) else set(session_id)
        all_nodes = self._driver.all_nodes()
        matched = [n for n in all_nodes if n.session_id in sids]
        return self._build_subgraph(matched)

    def get_versions(self, full_name: str) -> list[RuntimeVariable[Any]]:
        """Return all versions of a variable sorted oldest-first.

        Args:
            full_name (`str`):
                The namespaced variable name or bare variable name when no class name is set.

        Returns:
            `list[RuntimeVariable[Any]]`:
                Version 1 through latest, in order.
        """
        nodes = self._driver.get_nodes_by_name(full_name)
        nodes.sort(key=lambda v: v.version)
        return [RuntimeVariable(variable=v) for v in nodes]

    def get_latest_variable(self, full_name: str) -> RuntimeVariable[Any]:
        """Return the latest version of a variable.

        Args:
            full_name (`str`):
                The namespaced variable name or bare variable name when no class name is set.

        Returns:
            `RuntimeVariable`:
                The latest version of the variable.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        return RuntimeVariable(variable=self._resolve_variable(full_name))

    def bfs(
        self,
        full_node_id: str,
        direction: Literal["forward", "backward", "both"] = "forward",
        *,
        max_depth: int | None = None,
        op_ids: str | Iterable[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        categories: str | Iterable[str] | None = None,
        session_ids: str | Iterable[str] | None = None,
        include_sibling_inputs: bool = False,
    ) -> RuntimeGraph:
        """Breadth-first search from the specified node to collect a connected subgraph.

        Args:
            full_node_id (`str`):
                The full node identifier of the starting node.
            direction (`Literal["forward", "backward", "both"]`, defaults to `"forward"`):
                The direction of the search. ``"forward"`` follows outgoing
                edges, ``"backward"`` follows incoming edges, and ``"both"``
                computes the union of the forward and backward cones from the
                starting node.
            max_depth (`int | None`, optional):
                Maximum number of hops from the starting node.  When not
                provided, the search is unbounded and explores all
                reachable nodes.  A value of ``0`` returns only the start
                node. ``1`` returns direct neighbours, and so on.
            op_ids (`str | Iterable[str] | None`, optional):
                Operation filter. A single operation identifier or iterable of
                operation identifiers. Only edges whose operation identifier is in this
                set will be traversed.
            start_time (`str | None`, optional):
                Inclusive lower bound for the creation time of nodes. Neighbour nodes
                outside this bound are skipped (the start node is always
                included).
            end_time (`str | None`, optional):
                Inclusive upper bound for the creation time of nodes.
            categories (`str | Iterable[str] | None`, optional):
                Category filter. A single string or iterable of strings.
                Neighbour nodes whose category is not in this set are
                skipped (the start node is always included).
            session_ids (`str | Iterable[str] | None`, optional):
                Session filter. A single session identifier or iterable of
                session identifiers. Neighbour nodes whose session identifier
                is not in this set are skipped (the start node is always
                included).
            include_sibling_inputs (`bool`, defaults to `False`):
                When enabled, whenever a forward edge (with operation
                identifier) is traversed, all other incoming edges of
                current visited node sharing the same operation identifier 
                are added to the result, and their source nodes are recorded 
                as boundary nodes in the subgraph. 

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view of the traversal result.

        Raises:
            `ExecNetworkKeyError`:
                If the starting node does not exist in the graph.
        """
        if full_node_id not in self:
            raise ExecNetworkKeyError(
                f"The starting node '{full_node_id}' is not found in the graph."
            )

        cat_set = None
        if categories is not None:
            cat_set = {categories} if isinstance(categories, str) else set(categories)

        sid_set = None
        if session_ids is not None:
            sid_set = {session_ids} if isinstance(session_ids, str) else set(session_ids)

        op_set = None
        if op_ids is not None:
            op_set = {op_ids} if isinstance(op_ids, str) else set(op_ids)

        start = self._driver.get_node(full_node_id)
        visited_nodes = {full_node_id: start}
        
        # `boundary_nodes` holds identifiers that are added solely as
        # same-operation sibling inputs and must not be expanded. They stay
        # in `visited_nodes` so membership checks and edge collection treat
        # them uniformly. 
        # The queue only carries interior (expandable) nodes.
        boundary_nodes = set()
        visited_edges = {}
        visited_ops = {}

        # Sibling expansion only applies to forward traversal. For `"both"`,
        # it affects only the outgoing arm. 
        sibling_enabled = include_sibling_inputs and direction in ("forward", "both")
        # Memoize visited node and operation identifier pairs we have already
        # explored for same-operation sibling inputs, so that repeated
        # forward edges into the same target for the same operation do not rescan.
        sibling_processed = set()

        if direction == "both":
            initial_dirs = ("outgoing", "incoming")
        elif direction == "forward":
            initial_dirs = ("outgoing",)
        else:
            initial_dirs = ("incoming",)

        queue = [
            (full_node_id, 0, initial_dirs),
        ]

        def _neighbour_id(edge: OpEdge, d: str) -> str:
            """Return the neighbour node identifier of the given edge."""
            if d == "outgoing":
                return edge.target_full_node_id
            return edge.source_full_node_id

        def _pass_node_filters(node: Variable) -> bool:
            """Return whether a neighbour node satisfies the node-level filters."""
            if cat_set is not None and node.category not in cat_set:
                return False
            if start_time is not None and node.created_at < start_time:
                return False
            if end_time is not None and node.created_at > end_time:
                return False
            if sid_set is not None and node.session_id not in sid_set:
                return False
            return True

        def _store_edge(edge: OpEdge) -> None:
            """Record an edge and its owning operation without triggering siblings."""
            visited_edges[edge.edge_id] = edge
            if edge.op_id not in visited_ops:
                op = self._driver.get_operation(edge.op_id)
                assert op is not None, (
                    f"A dangling operation identifier '{edge.op_id}' is found "
                    f"on edge '{edge.edge_id}'. The graph may be damaged."
                )
                visited_ops[op.op_id] = op

        def _expand_siblings(forward_edge: OpEdge) -> None:
            """Pull in same-operation sibling input edges and their sources.

            It is invoked after a forward edge is traversed. Every other 
            incoming edge of the current visited node whose operation identifier 
            equals the operation identifier of the forward edge is added to the
            result, and its source is added as a boundary node when new.
            Nodes that already appear in visited nodes are left untouched 
            (and in particular are not demoted back to boundary status).
            """
            if not sibling_enabled:
                return
    
            key = (forward_edge.target_full_node_id, forward_edge.op_id)
            if key in sibling_processed:
                # This operation has already been processed.
                return

            sibling_processed.add(key)
            siblings = self._driver.get_edges_by_node(
                forward_edge.target_full_node_id,
                direction="incoming",
            )
            for sib in siblings:
                if sib.op_id != forward_edge.op_id:
                    continue
                if sib.edge_id == forward_edge.edge_id:
                    continue
                
                src_id = sib.source_full_node_id
                if src_id not in visited_nodes:
                    src = self._driver.get_node(src_id)
                    assert src is not None, (
                        f"A dangling node identifier '{src_id}' is found "
                        f"on edge '{sib.edge_id}'. The graph may be damaged."
                    )
                    if not _pass_node_filters(src):
                        continue
                    visited_nodes[src_id] = src
                    boundary_nodes.add(src_id)
                _store_edge(sib)

        def _collect_edge(edge: OpEdge, edge_dir: str) -> None:
            """Record an edge and, on forward traversal, trigger sibling expansion."""
            _store_edge(edge)
            if edge_dir == "outgoing":
                _expand_siblings(edge)

        while queue:
            current, depth, cur_dirs = queue.pop(0)
            for edge_dir in cur_dirs:
                edges = self._driver.get_edges_by_node(current, direction=edge_dir)
                for edge in edges:
                    if op_set is not None and edge.op_id not in op_set:
                        continue

                    neighbour_id = _neighbour_id(edge, edge_dir)
                    if neighbour_id in visited_nodes:
                        _collect_edge(edge, edge_dir)
                        # A node added as boundary is promoted to
                        # interior the first time the primary forward walk
                        # reaches it via an ordinary edge.
                        if (
                            edge_dir == "outgoing"
                            and neighbour_id in boundary_nodes
                            and (max_depth is None or depth + 1 <= max_depth)
                        ):
                            boundary_nodes.discard(neighbour_id)
                            next_dirs = (
                                (edge_dir,) if direction == "both" else cur_dirs
                            )
                            queue.append((neighbour_id, depth + 1, next_dirs))
                        continue

                    if max_depth is not None and depth + 1 > max_depth:
                        continue

                    node = self._driver.get_node(neighbour_id)
                    assert node is not None, (
                        f"A dangling node identifier '{neighbour_id}' is found "
                        f"on edge '{edge.edge_id}'. The graph may be damaged."
                    )

                    if not _pass_node_filters(node):
                        continue

                    _collect_edge(edge, edge_dir)
                    visited_nodes[neighbour_id] = node

                    next_dirs = (edge_dir,) if direction == "both" else cur_dirs
                    queue.append((neighbour_id, depth + 1, next_dirs))

        # Note: the returned graph is not guaranteed to be
        # the induced subgraph on visited nodes. It only contains the
        # edges actually walked by the BFS plus any one-hop same-op sibling
        # edges produced. Two classes of edges are
        # intentionally left out:
        #   * The search direction is both backward and forward: 
        #     edges from a backward-cone node directly to a forward-cone node 
        #     are not enumerated (backward-cone nodes only expand along incoming 
        #     edges and forward-cone nodes only along outgoing).
        #   * Sibling expansion is enabled: boundary nodes
        #     do not expand their other outgoing edges, so edges whose
        #     source is a boundary node are not collected, and sibling 
        #     expansion never cascades through a boundary node.
        return RuntimeGraph(
            nodes=[RuntimeVariable(variable=v) for v in visited_nodes.values()],
            edges=[RuntimeEdge(edge=e) for e in visited_edges.values()],
            ops=[RuntimeOp(op=o) for o in visited_ops.values()],
        )

    def get_operation_subgraphs(
        self,
        full_name: str,
        version: int | None = None,
    ) -> list[RuntimeGraph]:
        """Get subgraphs of direct parent operations grouped by category.

        For the given variable (latest version unless version is specified), 
        find all incoming edges, group them by operation category, 
        and return one runtime graph per group.

        Args:
            full_name (`str`):
                The namespaced variable name or bare variable name when no class name is set.
            version (`int | None`, optional):
                Specific version. If not provided, the latest version is used.

        Returns:
            `list[RuntimeGraph]`:
                One subgraph per distinct operation category.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        target_var = self._resolve_variable(full_name, version=version)

        target_full_id = target_var.full_node_id
        in_edges = self._driver.get_edges_by_node(target_full_id, direction="incoming")

        groups = {}
        for edge in in_edges:
            cat = edge.category
            if cat not in groups:
                groups[cat] = {"nodes": {}, "edges": {}, "ops": {}}
            g = groups[cat]
            g["edges"][edge.edge_id] = edge
            op = self._driver.get_operation(edge.op_id)
            assert op is not None, (
                f"A dangling operation identifier '{edge.op_id}' is found " 
                f"on edge '{edge.edge_id}'. The graph may be damaged."
            )
            g["ops"][op.op_id] = op
            src = self._driver.get_node(edge.source_full_node_id)
            assert src is not None, (
                f"A dangling node identifier '{edge.source_full_node_id}' is found " 
                f"on edge '{edge.edge_id}'. The graph may be damaged."
            )
            g["nodes"][src.full_node_id] = src
            g["nodes"][target_full_id] = target_var

        result = []
        for g in groups.values():
            result.append(
                RuntimeGraph(
                    nodes=[RuntimeVariable(variable=v) for v in g["nodes"].values()],
                    edges=[RuntimeEdge(edge=e) for e in g["edges"].values()],
                    ops=[RuntimeOp(op=o) for o in g["ops"].values()],
                )
            )
        return result

    def get_child_subgraphs(
        self,
        full_name: str,
        version: int | None = None,
    ) -> list[RuntimeGraph]:
        """Get operation subgraphs centred on each direct child node.

        Args:
            full_name (`str`):
                Namespaced parent variable name. If no class name is set, 
                the bare variable name is used.
            version (`int | None`, optional):
                Specific version. If not provided, the latest version is used.

        Returns:
            `list[RuntimeGraph]`:
                Operation subgraphs for each child.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        parent = self._resolve_variable(full_name, version=version)

        out_edges = self._driver.get_edges_by_node(parent.full_node_id, direction="outgoing")
        child_full_names = set()
        result = []
        for edge in out_edges:
            child = self._driver.get_node(edge.target_full_node_id)
            assert child is not None, (
                f"A dangling node identifier '{edge.target_full_node_id}' is found " 
                f"on edge '{edge.edge_id}'. The graph may be damaged."
            )

            # The execution graph is a directed multigraph. 
            if child.full_name not in child_full_names:
                child_full_names.add(child.full_name)
                result.extend(
                    self.get_operation_subgraphs(
                        child.full_name, 
                        version=child.version
                    )
                )
        return result

    def time_range(self) -> tuple[str, str] | None:
        """Return the earliest and latest creation time among all variables.

        Returns:
            `tuple[str, str] | None`:
                The earliest and latest creation time of variables in the 
                execution graph if the graph is not empty.
        """
        nodes = self._driver.all_nodes()
        if not nodes:
            return None
        times = [n.created_at for n in nodes]
        return (min(times), max(times))

    def filter_by_time(
        self,
        start: str | None = None,
        end: str | None = None,
        exclude: bool = False,
    ) -> RuntimeGraph:
        """Return a subgraph of variables within (or outside) a time range.

        Args:
            start (`str | None`, optional):
                Inclusive lower bound for the creation time of nodes.
                If not provided, it means no lower bound.
            end (`str | None`, optional):
                Inclusive upper bound for the creation time of nodes.  If not provided,
                it means no upper bound.
            exclude (`bool`, defaults to `False`):
                If enabled, return variables outside the time range instead.

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view.
        """
        all_nodes = self._driver.all_nodes()
        if exclude:
            matched = [
                n for n in all_nodes
                if (start is not None and n.created_at < start)
                or (end is not None and n.created_at > end)
            ]
        else:
            matched = [
                n for n in all_nodes
                if (start is None or n.created_at >= start)
                and (end is None or n.created_at <= end)
            ]

        return self._build_subgraph(matched)

    def filter_by_category(
        self,
        category: str | Iterable[str],
    ) -> RuntimeGraph:
        """Return a subgraph of variables matching the given category or categories.

        Args:
            category (`str | Iterable[str]`):
                A single category string or an iterable of category strings.
                Nodes whose category is in this set are kept.

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view.
        """
        cats = {category} if isinstance(category, str) else set(category)
        all_nodes = self._driver.all_nodes()
        matched = [n for n in all_nodes if n.category in cats]
        return self._build_subgraph(matched)

    def filter_by_operation(
        self,
        op_id: str | Iterable[str],
    ) -> RuntimeGraph:
        """Return a subgraph induced by edges belonging to the given operation(s).

        It collects every edge whose operation identifier is in the given set, 
        includes the nodes at both endpoints.

        Args:
            op_id (`str | Iterable[str]`):
                A single operation identifier or an iterable of operation
                identifiers.

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view containing the matched edges,
                their endpoint nodes, and the corresponding operations.
        """
        op_set = {op_id} if isinstance(op_id, str) else set(op_id)
        matched_edges = []
        for oid in op_set:
            matched_edges.extend(self._driver.get_edges_by_operation(oid))

        node_ids = set()
        visited_op_ids = set()
        matched_ops = []
        for edge in matched_edges:
            node_ids.add(edge.source_full_node_id)
            node_ids.add(edge.target_full_node_id)
            if edge.op_id not in visited_op_ids:
                visited_op_ids.add(edge.op_id)
                op = self._driver.get_operation(edge.op_id)
                assert op is not None, (
                    f"A dangling operation identifier '{edge.op_id}' is found "
                    f"on edge '{edge.edge_id}'. The graph may be damaged."
                )
                matched_ops.append(op)

        matched_nodes = []
        for nid in node_ids:
            node = self._driver.get_node(nid)
            assert node is not None, (
                f"A dangling node identifier '{nid}' is found in the graph. "
                "The graph may be damaged."
            )
            matched_nodes.append(node)

        return RuntimeGraph(
            nodes=[RuntimeVariable(variable=v) for v in matched_nodes],
            edges=[RuntimeEdge(edge=e) for e in matched_edges],
            ops=[RuntimeOp(op=o) for o in matched_ops],
        )

    def search_sessions(
        self,
        *,
        name_pattern: str | None = None,
        category: str | Iterable[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[RuntimeSession]:
        """Search sessions by combining multiple optional filters with AND.

        When no filters are given, all sessions are returned.

        Args:
            name_pattern (`str | None`, optional):
                Regular expression matched against each session's name.  
                Sessions whose name is not provided are skipped when 
                this filter is active.
            category (`str | Iterable[str] | None`, optional):
                A single category string or an iterable of category
                strings.  A session matches if its category is in the set.
            start_time (`str | None`, optional):
                Inclusive lower bound for the creation time of sessions.
            end_time (`str | None`, optional):
                Inclusive upper bound for the creation time of sessions.

        Returns:
            `list[RuntimeSession]`:
                Matching sessions sorted by the creation time ascending.
        """
        compiled = re.compile(name_pattern) if name_pattern is not None else None

        cat_set = None
        if category is not None:
            cat_set = {category} if isinstance(category, str) else set(category)

        results = []
        for s in self._driver.all_sessions():
            if cat_set is not None and s.category not in cat_set:
                continue
            if start_time is not None and s.created_at < start_time:
                continue
            if end_time is not None and s.created_at > end_time:
                continue
            if compiled is not None:
                if s.session_name is None or not compiled.search(s.session_name):
                    continue
            results.append(s)

        results.sort(key=lambda s: s.created_at)
        return [RuntimeSession(session=s) for s in results]

    def search_operations(
        self,
        *,
        name_pattern: str | None = None,
        category: str | Iterable[str] | None = None,
        session_ids: str | Iterable[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[RuntimeOp]:
        """Search operations by combining multiple optional filters with AND.

        Args:
            name_pattern (`str | None`, optional):
                Regular expression matched against the operation name.  
                Operations whose name is not provided are skipped when 
                this filter is active.
            category (`str | Iterable[str] | None`, optional):
                A single category string or an iterable of category
                strings.  An operation matches if its category is in the set.
            session_ids (`str | Iterable[str] | None`, optional):
                A single session identifier or an iterable of session
                identifiers.  Only operations belonging to those sessions
                are returned.
            start_time (`str | None`, optional):
                Inclusive lower bound for the creation time of operations.
            end_time (`str | None`, optional):
                Inclusive upper bound for the creation time of operations.

        Returns:
            `list[RuntimeOp]`:
                Matching operations sorted by the creation time ascending.
        """
        compiled = re.compile(name_pattern) if name_pattern is not None else None

        cat_set = None
        if category is not None:
            cat_set = {category} if isinstance(category, str) else set(category)

        sid_set = None
        if session_ids is not None:
            sid_set = {session_ids} if isinstance(session_ids, str) else set(session_ids)

        results = []
        for op in self._driver.all_operations():
            if cat_set is not None and op.category not in cat_set:
                continue
            if sid_set is not None and op.session_id not in sid_set:
                continue
            if start_time is not None and op.created_at < start_time:
                continue
            if end_time is not None and op.created_at > end_time:
                continue
            if compiled is not None:
                if op.op_name is None or not compiled.search(op.op_name):
                    continue
            results.append(op)

        results.sort(key=lambda o: o.created_at)
        return [RuntimeOp(op=o) for o in results]

    def search_variables(
        self,
        *,
        name_pattern: str | None = None,
        category: str | Iterable[str] | None = None,
        class_name: str | None = None,
        session_ids: str | Iterable[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[RuntimeVariable[Any]]:
        """Search variable nodes by combining multiple optional filters with AND.

        Args:
            name_pattern (`str | None`, optional):
                Regular expression matched against the variable full name.  
            category (`str | Iterable[str] | None`, optional):
                A single category string or an iterable of category
                strings. A variable matches if its category is in the set.
            class_name (`str | None`, optional):
                Exact match on the variable class name.
            session_ids (`str | Iterable[str] | None`, optional):
                A single session identifier or an iterable of session
                identifiers. Only variables belonging to those sessions
                are returned.
            start_time (`str | None`, optional):
                Inclusive lower bound for the creation time of variables.
            end_time (`str | None`, optional):
                Inclusive upper bound for the creation time of variables.

        Returns:
            `list[RuntimeVariable[Any]]`:
                Matching variables sorted by the creation time ascending.
        """
        compiled = re.compile(name_pattern) if name_pattern is not None else None
        cat_set = None
        if category is not None:
            cat_set = {category} if isinstance(category, str) else set(category)

        sid_set = None
        if session_ids is not None:
            sid_set = {session_ids} if isinstance(session_ids, str) else set(session_ids)

        results = []
        for n in self._driver.all_nodes():
            if cat_set is not None and n.category not in cat_set:
                continue
            if class_name is not None and n.class_name != class_name:
                continue
            if sid_set is not None and n.session_id not in sid_set:
                continue
            if start_time is not None and n.created_at < start_time:
                continue
            if end_time is not None and n.created_at > end_time:
                continue
            if compiled is not None and not compiled.search(n.full_name):
                continue
            results.append(n)

        results.sort(key=lambda v: v.created_at)
        return [RuntimeVariable(variable=v) for v in results]

    def search_edges(
        self,
        *,
        category: str | Iterable[str] | None = None,
        op_ids: str | Iterable[str] | None = None,
        session_ids: str | Iterable[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[RuntimeEdge]:
        """Search edges by combining multiple optional filters with AND.

        Args:
            category (`str | Iterable[str] | None`, optional):
                A single category string or an iterable of category
                strings. An edge matches if its category is in the set.
            op_ids (`str | Iterable[str] | None`, optional):
                A single operation identifier or an iterable of operation
                identifiers. Only edges belonging to those operations are
                returned.
            session_ids (`str | Iterable[str] | None`, optional):
                A single session identifier or an iterable of session
                identifiers. Only edges belonging to those sessions are
                returned.
            start_time (`str | None`, optional):
                Inclusive lower bound for the creation time of edges.
            end_time (`str | None`, optional):
                Inclusive upper bound for the creation time of edges.

        Returns:
            `list[RuntimeEdge]`:
                Matching edges sorted by the creation time ascending.
        """
        cat_set = None
        if category is not None:
            cat_set = {category} if isinstance(category, str) else set(category)

        op_set = None
        if op_ids is not None:
            op_set = {op_ids} if isinstance(op_ids, str) else set(op_ids)

        sid_set = None
        if session_ids is not None:
            sid_set = {session_ids} if isinstance(session_ids, str) else set(session_ids)

        edges = []
        if op_set is None:
            edges = self._driver.all_edges()
        else:
            for op_id in op_set:
                edges.extend(self._driver.get_edges_by_operation(op_id))

        results = []
        for e in edges:
            if cat_set is not None and e.category not in cat_set:
                continue
            if sid_set is not None and e.session_id not in sid_set:
                continue
            if start_time is not None and e.created_at < start_time:
                continue
            if end_time is not None and e.created_at > end_time:
                continue
            results.append(e)

        results.sort(key=lambda e: e.created_at)
        return [RuntimeEdge(edge=e) for e in results]

    def get_leaf_nodes(self) -> list[RuntimeVariable[Any]]:
        """Return all nodes with zero out-degree (no outgoing edges).

        Returns:
            `list[RuntimeVariable[Any]]`:
                Leaf nodes of the graph.
        """
        sources = {e.source_full_node_id for e in self._driver.all_edges()}
        return [
            RuntimeVariable(variable=n)
            for n in self._driver.all_nodes()
            if n.full_node_id not in sources
        ]

    def get_root_nodes(self) -> list[RuntimeVariable[Any]]:
        """Return all nodes with zero in-degree (no incoming edges).

        Returns:
            `list[RuntimeVariable[Any]]`:
                Root nodes of the graph.
        """
        targets = {e.target_full_node_id for e in self._driver.all_edges()}
        return [
            RuntimeVariable(variable=n)
            for n in self._driver.all_nodes()
            if n.full_node_id not in targets
        ]

    def get_all_nodes(self) -> list[RuntimeVariable[Any]]:
        """Return all variable nodes wrapped as runtime handles.

        Returns:
            `list[RuntimeVariable[Any]]`:
                Every node in the graph.
        """
        return [RuntimeVariable(variable=v) for v in self._driver.all_nodes()]

    def get_all_edges(self) -> list[RuntimeEdge]:
        """Return all edges wrapped as runtime handles.

        Returns:
            `list[RuntimeEdge]`:
                Every edge in the graph.
        """
        return [RuntimeEdge(edge=e) for e in self._driver.all_edges()]

    def get_all_operations(self) -> list[RuntimeOp]:
        """Return all operations wrapped as runtime handles.

        Returns:
            `list[RuntimeOp]`:
                Every operation in the graph.
        """
        return [RuntimeOp(op=o) for o in self._driver.all_operations()]

    def to_runtime_graph(self) -> RuntimeGraph:
        """Return the full graph as a read-only runtime graph snapshot.

        Returns:
            `RuntimeGraph`:
                A read-only graph view containing all nodes, edges, and operations.
        """
        return RuntimeGraph(
            nodes=self.get_all_nodes(),
            edges=self.get_all_edges(),
            ops=self.get_all_operations(),
        )

    def induced_subgraph(self, full_node_ids: Iterable[str]) -> RuntimeGraph:
        """Return the induced subgraph over a given set of node identifiers.

        Nodes not present in the graph are silently skipped.

        Args:
            full_node_ids (`Iterable[str]`):
                The full node identifiers to include.

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view.
        """
        id_set = set(full_node_ids)
        nodes = [
            n for n in self._driver.all_nodes()
            if n.full_node_id in id_set
        ]
        return self._build_subgraph(nodes)

    def __len__(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._driver.all_nodes())

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._driver.all_nodes())

    @property
    def edge_count(self) -> int:
        """Return the number of edges in the graph."""
        return len(self._driver.all_edges())

    @property
    def op_count(self) -> int:
        """Return the number of operations in the graph."""
        return len(self._driver.all_operations())

    @property
    def session_count(self) -> int:
        """Return the number of sessions in the graph."""
        return len(self._driver.all_sessions())

    @property
    def is_empty(self) -> bool:
        """Check whether the graph contains no nodes."""
        return len(self._driver.all_nodes()) == 0

    def visualize(self, backend: str = "graphviz", **kwargs: Any) -> Any:
        """Render the graph using a registered visualization backend.

        Args:
            backend (`str`, defaults to `"graphviz"`):
                Name of the visualization backend.
            **kwargs:
                Forwarded to the backend function.

        Returns:
            `Any`:
                The return value of the visualization backend.
        """
        if backend not in _VISUAL_BACKENDS:
            raise ValueError(
                f"'{backend}' is not a supported visualization backend. "
                "Available visualization backends " 
                f"are {', '.join(list(_VISUAL_BACKENDS.keys()))}."
            )
        nodes = [RuntimeVariable(variable=v) for v in self._driver.all_nodes()]
        edges = [RuntimeEdge(edge=e) for e in self._driver.all_edges()]
        return _VISUAL_BACKENDS[backend](
            nodes, 
            edges, 
            **kwargs
        )

    def export_graph(self) -> dict[str, Any]:
        """Export the full graph to a JSON-compatible dictionary.

        Returns:
            `dict[str, Any]`:
                Serialized graph including graph data.
        """
        return self.model_dump()

    @classmethod
    def import_graph(cls, data: dict[str, Any]) -> Self:
        """Reconstruct an execution graph from a serialized dictionary.

        Args:
            data (`dict[str, Any]`):
                Dictionary produced by :meth:`export_graph`.

        Returns:
            `Self`:
                The reconstructed graph.
        """
        return cls.model_validate(data)

    def _resolve_variable(
        self, 
        full_name: str, 
        version: int | None = None
    ) -> Variable:
        """Look up a variable by its full name and a specific version.

        Args:
            full_name (`str`):
                The namespaced variable name or bare variable name when no class name is set.
            version (`int | None`, optional):
                Specific version. If not provided, the latest version is used.

        Returns:
            `Variable`:
                The variable.

        Raises:
            `ExecNetworkKeyError`:
                If the variable is not found in the graph.
        """
        if version is not None:
            variable = self._driver.get_node(f"{full_name}@{version}")
            if variable is None:
                raise ExecNetworkKeyError(
                    f"The variable '{full_name}@{version}' is not found in the graph."
                )
            return variable
        
        variable = self._driver.get_latest_node(full_name)
        if variable is None:
            raise ExecNetworkKeyError(
                f"The variable '{full_name}' is not found in the graph."
            )
        return variable

    def _reachable_closure(
        self,
        full_node_id: str,
        direction: Literal["incoming", "outgoing"] = "outgoing",
        max_depth: int | None = None,
    ) -> set[str]:
        """Collect full node identifiers reachable by following edges in one direction.

        Args:
            full_node_id (`str`):
                Starting full node identifier.
            direction (`Literal["incoming", "outgoing"]`, defaults to `"outgoing"`):
                The direction to traverse the graph.
            max_depth (`int | None`, optional):
                Maximum number of hops from the starting node.  When not
                provided, the traversal is unbounded and explores all
                reachable nodes.  A value of ``0`` returns only the start
                node.  ``1`` returns the start node and its direct
                neighbours, and so on.

        Returns:
            `set[str]`:
                The start node and all reachable nodes in the closure.

        Raises:
            `ExecNetworkKeyError`:
                If the given full node identifier is not found in the graph.
        """
        if full_node_id not in self:
            raise ExecNetworkKeyError(
                f"The full node identifier '{full_node_id}' is not found in the graph."
            )

        visited = set()
        queue = [(full_node_id, 0)]
        while queue:
            current, depth = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if max_depth is not None and depth >= max_depth:
                continue
            for edge in self._driver.get_edges_by_node(current, direction=direction):
                neighbour = (
                    edge.source_full_node_id
                    if direction == "incoming"
                    else edge.target_full_node_id
                )
                if neighbour not in visited:
                    queue.append((neighbour, depth + 1))
        return visited

    def _build_subgraph(self, nodes: list[Variable]) -> RuntimeGraph:
        """Build a runtime graph from a filtered list of schema variables.

        Args:
            nodes (`list[Variable]`):
                The list of variables to include in the subgraph.

        Returns:
            `RuntimeGraph`:
                A read-only subgraph view.
        """
        node_ids = {n.full_node_id for n in nodes}
        all_edges = self._driver.all_edges()
        matched_edges = [
            e for e in all_edges
            if e.source_full_node_id in node_ids
            and e.target_full_node_id in node_ids
        ]

        visited_op_ids = set() 
        matched_ops = []
        for edge in matched_edges:
            if edge.op_id not in visited_op_ids:
                visited_op_ids.add(edge.op_id)
                op = self._driver.get_operation(edge.op_id)
                assert op is not None, (
                    f"A dangling operation identifier '{edge.op_id}' is found " 
                    f"on edge '{edge.edge_id}'. The graph may be damaged."
                )
                matched_ops.append(op)

        return RuntimeGraph(
            nodes=[RuntimeVariable(variable=v) for v in nodes],
            edges=[RuntimeEdge(edge=e) for e in matched_edges],
            ops=[RuntimeOp(op=o) for o in matched_ops],
        )
