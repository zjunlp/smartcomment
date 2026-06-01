"""Abstract base class for graph storage drivers."""

from abc import ABC, abstractmethod
from ..schema.operation import OpEdge, OpRecord
from ..schema.session import Session
from ..schema.variable import Variable
from typing import (
    Any, 
    Literal, 
    Self,
)


class GraphDriver(ABC):
    """Unified storage interface for execution graph data."""

    @abstractmethod
    def add_node(self, variable: Variable) -> None:
        """Insert a variable node.

        Args:
            variable (`Variable`):
                The variable to store.

        Raises:
            `ValueError`:
                If a node with the same full node identifier already exists.
        """
        ...

    @abstractmethod
    def remove_node(self, full_node_id: str) -> None:
        """Remove a variable node and cascade-delete its connected edges.

        Args:
            full_node_id (`str`):
                The full node identifier to remove.
        """
        ...

    @abstractmethod
    def has_node(self, full_node_id: str) -> bool:
        """Check whether a node exists in the graph.

        Args:
            full_node_id (`str`):
                The full node identifier to check.

        Returns:
            `bool`:
                ``True`` if the node exists, ``False`` otherwise.
        """
        ...

    @abstractmethod
    def get_node(self, full_node_id: str) -> Variable | None:
        """Retrieve a single node by its full node identifier.

        Args:
            full_node_id (`str`):
                The full node identifier to look up.

        Returns:
            `Variable | None`:
                The variable if found.
        """
        ...

    @abstractmethod
    def get_nodes_by_name(self, full_name: str) -> list[Variable]:
        """Return all versions of a variable sorted by version.

        Args:
            full_name (`str`):
                The namespaced variable name or bare variable name when no class name is set.

        Returns:
            `list[Variable]`:
                All versions, sorted ascending.
        """
        ...

    @abstractmethod
    def get_latest_node(self, full_name: str) -> Variable | None:
        """Return the latest version of a variable.

        Args:
            full_name (`str`):
                The namespaced variable name or bare variable name
                when no class name is set.

        Returns:
            `Variable | None`:
                The latest version if found.
        """
        ...

    @abstractmethod
    def add_edge(self, edge: OpEdge) -> None:
        """Insert a directed edge.

        Args:
            edge (`OpEdge`):
                The edge to store.

        Raises:
            `ValueError`:
                If an edge with the same edge identifier already exists.
        """
        ...

    @abstractmethod
    def remove_edge(self, edge_id: str) -> None:
        """Remove an edge.

        Args:
            edge_id (`str`):
                The edge identifier to remove.
        """
        ...

    @abstractmethod
    def get_edge(self, edge_id: str) -> OpEdge | None:
        """Retrieve a single edge by its identifier.

        Args:
            edge_id (`str`):
                The edge identifier to look up.

        Returns:
            `OpEdge | None`:
                The edge if found.
        """
        ...

    @abstractmethod
    def get_edges_by_node(
        self,
        full_node_id: str,
        direction: Literal["incoming", "outgoing"] = "outgoing",
    ) -> list[OpEdge]:
        """Return edges connected to a node.

        Args:
            full_node_id (`str`):
                The full node identifier to query.
            direction (`Literal["incoming", "outgoing"]`, defaults to `"outgoing"`):
                The direction of the edges to query.

        Returns:
            `list[OpEdge]`:
                Matching edges.
        """
        ...

    @abstractmethod
    def get_edges_by_operation(self, op_id: str) -> list[OpEdge]:
        """Return edges belonging to an operation.

        Args:
            op_id (`str`):
                The operation identifier to query.

        Returns:
            `list[OpEdge]`:
                Matching edges.
        """
        ...

    @abstractmethod
    def add_operation(self, op: OpRecord) -> None:
        """Insert an operation record.

        Args:
            op (`OpRecord`):
                The operation to store.

        Raises:
            `ValueError`:
                If an operation with the same operation identifier already exists.
        """
        ...

    @abstractmethod
    def remove_operation(self, op_id: str) -> None:
        """Remove an operation and cascade-delete its edges.

        Args:
            op_id (`str`):
                The operation identifier to remove.
        """
        ...

    @abstractmethod
    def get_operation(self, op_id: str) -> OpRecord | None:
        """Retrieve a single operation by its identifier.

        Args:
            op_id (`str`):
                The operation identifier to look up.

        Returns:
            `OpRecord | None`:
                The operation if found.
        """
        ...

    @abstractmethod
    def add_session(self, session: Session) -> None:
        """Insert a session record.

        Args:
            session (`Session`):
                The session to store.

        Raises:
            `ValueError`:
                If a session with the same session identifier already exists.
        """
        ...

    @abstractmethod
    def remove_session(self, session_id: str) -> None:
        """Remove a session and cascade-delete its operations, nodes, and edges.

        Args:
            session_id (`str`):
                The session identifier to remove.
        """
        ...

    @abstractmethod
    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a single session by id.

        Args:
            session_id (`str`):
                The session identifier to look up.

        Returns:
            `Session | None`:
                The session if found.
        """
        ...

    @abstractmethod
    def all_nodes(self) -> list[Variable]:
        """Return every variable in the graph.

        Returns:
            `list[Variable]`:
                All stored variables.
        """
        ...

    @abstractmethod
    def all_edges(self) -> list[OpEdge]:
        """Return every edge in the graph.

        Returns:
            `list[OpEdge]`:
                All stored edges.
        """
        ...

    @abstractmethod
    def all_operations(self) -> list[OpRecord]:
        """Return every operation in the graph.

        Returns:
            `list[OpRecord]`:
                All stored operations.
        """
        ...

    @abstractmethod
    def all_sessions(self) -> list[Session]:
        """Return every session in the graph.

        Returns:
            `list[Session]`:
                All stored sessions.
        """
        ...

    @abstractmethod
    def serialize(self) -> dict[str, Any]:
        """Serialize the driver state to a JSON-compatible dictionary.

        Returns:
            `dict[str, Any]`:
                Serialized state.
        """
        ...

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict[str, Any]) -> Self:
        """Reconstruct a driver from serialized state.

        Args:
            data (`dict[str, Any]`):
                Dictionary produced by corresponding `serialize` method.

        Returns:
            `Self`:
                A new driver with restored state.
        """
        ...
