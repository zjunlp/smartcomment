"""Pure-Python in-memory graph driver with full index structures."""

import threading
from collections import defaultdict
from .base import GraphDriver
from ..schema.operation import OpEdge, OpRecord
from ..schema.session import Session
from ..schema.variable import Variable
from typing import (
    Any, 
    Literal, 
    Self,
)


class InMemoryGraphDriver(GraphDriver):
    """Store graph data in plain Python dictionaries with adjacency-list indexes. 
    This implementation is thread-safe and reentrant."""

    def __init__(self) -> None:
        # Use a reentrant lock because `remove_node` and `remove_session` cascade into
        # `remove_edge` and `remove_operation` while already holding the lock.
        self._lock = threading.RLock()

        # Map of full node identifier to variable.
        self._nodes: dict[str, Variable] = {}
        # Map of edge identifier to edge.
        self._edges: dict[str, OpEdge] = {}
        # Map of operation identifier to operation.
        self._operations: dict[str, OpRecord] = {}
        # Map of session identifier to session.
        self._sessions: dict[str, Session] = {}

        # Map of full name to list of full node identifiers ordered by version.
        self._full_name_to_node_ids: dict[str, list[str]] = defaultdict(list)

        # Map of full node identifier to list of incoming edge identifiers.
        self._node_to_in_edges: dict[str, set[str]] = defaultdict(set)
        # Map of full node identifier to list of outgoing edge identifiers.
        self._node_to_out_edges: dict[str, set[str]] = defaultdict(set)

        # Cascade indexes.
        self._session_to_node_ids: dict[str, set[str]] = defaultdict(set)
        self._session_to_op_ids: dict[str, set[str]] = defaultdict(set)
        self._op_to_edge_ids: dict[str, set[str]] = defaultdict(set)

    def add_node(self, variable: Variable) -> None:
        with self._lock:
            nid = variable.full_node_id
            if nid in self._nodes:
                raise ValueError(
                    f"Node '{nid}' already exists in the graph. "
                    "Use `remove_node` before re-inserting."
                )

            if variable.session_id not in self._sessions:
                raise ValueError(
                    f"Session '{variable.session_id}' is not found in the graph. "
                    "Use `add_session` before adding a node."
                )

            self._nodes[nid] = variable
            self._full_name_to_node_ids[variable.full_name].append(nid)
            self._session_to_node_ids[variable.session_id].add(nid)

    def remove_node(self, full_node_id: str) -> None:
        with self._lock: 
            node = self._nodes.pop(full_node_id, None)
            if node is None:
                return

            # Clean up full name to node identifier index.
            ids = self._full_name_to_node_ids[node.full_name]
            ids.remove(full_node_id)
            # If the removed node is the earliest version,  
            # we need to clean up the mapping from full name to node identifiers.
            if not ids:
                del self._full_name_to_node_ids[node.full_name]

            # Clean up session to node identifier index.
            sn = self._session_to_node_ids.get(node.session_id)
            if sn is not None:
                sn.discard(full_node_id)
                if not sn:
                    del self._session_to_node_ids[node.session_id]

            # Cascade-remove all connected edges. 
            # Note that some nodes may have no adjacency bucket
            # because they are not connected to any other nodes.
            for eid in list(self._node_to_in_edges.pop(full_node_id, set())):
                self.remove_edge(eid)
            for eid in list(self._node_to_out_edges.pop(full_node_id, set())):
                self.remove_edge(eid)

    def has_node(self, full_node_id: str) -> bool:
        with self._lock:
            return full_node_id in self._nodes

    def get_node(self, full_node_id: str) -> Variable | None:
        with self._lock:
            return self._nodes.get(full_node_id)

    def get_nodes_by_name(self, full_name: str) -> list[Variable]:
        with self._lock:
            ids = self._full_name_to_node_ids.get(full_name, [])
            nodes = [self._nodes[nid] for nid in ids if nid in self._nodes]
            nodes.sort(key=lambda v: v.version)
            return nodes

    def get_latest_node(self, full_name: str) -> Variable | None:
        with self._lock:
            ids = self._full_name_to_node_ids.get(full_name, [])
            if not ids:
                return None
            return self._nodes.get(ids[-1])

    def add_edge(self, edge: OpEdge) -> None:
        with self._lock:
            eid = edge.edge_id
            if eid in self._edges:
                raise ValueError(
                    f"Edge '{eid}' already exists in the graph. "
                    "Use `remove_edge` before re-inserting."
                )

            if edge.session_id not in self._sessions:
                raise ValueError(
                    f"Session '{edge.session_id}' is not found in the graph. "
                    "Use `add_session` before adding an edge."
                )
            if edge.op_id not in self._operations:
                raise ValueError(
                    f"Operation '{edge.op_id}' is not found in the graph. "
                    "Use `add_operation` before adding an edge."
                )
            if edge.source_full_node_id not in self._nodes:
                raise ValueError(
                    f"Source node '{edge.source_full_node_id}' is not found in the graph. "
                    "Use `add_node` before adding an edge."
                )
            if edge.target_full_node_id not in self._nodes:
                raise ValueError(
                    f"Target node '{edge.target_full_node_id}' is not found in the graph. "
                    "Use `add_node` before adding an edge."
                )

            self._edges[eid] = edge
            self._node_to_out_edges[edge.source_full_node_id].add(eid)
            self._node_to_in_edges[edge.target_full_node_id].add(eid)
            self._op_to_edge_ids[edge.op_id].add(eid)

    def remove_edge(self, edge_id: str) -> None:
        with self._lock:  
            edge = self._edges.pop(edge_id, None)
            if edge is None:
                return

            # Clean up adjacency indexes.
            # Removing a node will trigger the removal of all corresponding out-edges and in-edges.
            # In this case, the mappings from node to out-edges and in-edges have been removed.
            # Therefore, we use `get` method to avoid `KeyError`.
            out_set = self._node_to_out_edges.get(edge.source_full_node_id)
            if out_set is not None:
                out_set.discard(edge_id)
                if not out_set:
                    del self._node_to_out_edges[edge.source_full_node_id]
            in_set = self._node_to_in_edges.get(edge.target_full_node_id)
            if in_set is not None:
                in_set.discard(edge_id)
                if not in_set:
                    del self._node_to_in_edges[edge.target_full_node_id]

            # Clean up operation to edge index.
            # The processing logic is similar to the above.
            op_edges = self._op_to_edge_ids.get(edge.op_id)
            if op_edges is not None:
                op_edges.discard(edge_id)
                if not op_edges:
                    del self._op_to_edge_ids[edge.op_id]

    def get_edge(self, edge_id: str) -> OpEdge | None:
        with self._lock:
            return self._edges.get(edge_id)

    def get_edges_by_node(
        self, 
        full_node_id: str, 
        direction: Literal["incoming", "outgoing"] = "outgoing",
    ) -> list[OpEdge]:
        with self._lock:
            if direction == "incoming":
                ids = self._node_to_in_edges.get(full_node_id, set())
            elif direction == "outgoing":
                ids = self._node_to_out_edges.get(full_node_id, set())
            else:
                raise ValueError(
                    "Direction must be either 'incoming' or 'outgoing' " 
                    f"but '{direction}' is given."
                )
            return [self._edges[eid] for eid in ids if eid in self._edges]

    def get_edges_by_operation(self, op_id: str) -> list[OpEdge]:
        """Return edges belonging to an operation.

        Args:
            op_id (`str`):
                The operation identifier to query.

        Returns:
            `list[OpEdge]`:
                Matching edges.
        """
        with self._lock:
            ids = self._op_to_edge_ids.get(op_id, set())
            return [self._edges[eid] for eid in ids if eid in self._edges]

    def add_operation(self, op: OpRecord) -> None:
        with self._lock:
            if op.op_id in self._operations:
                raise ValueError(
                    f"Operation '{op.op_id}' already exists in the graph. "
                    "Duplicate operation insertion is not allowed."
                )
            
            if op.session_id not in self._sessions:
                raise ValueError(
                    f"Session '{op.session_id}' is not found in the graph. "
                    "Use `add_session` before adding an operation."
                )

            self._operations[op.op_id] = op
            self._session_to_op_ids[op.session_id].add(op.op_id)

    def remove_operation(self, op_id: str) -> None:
        with self._lock: 
            op = self._operations.pop(op_id, None)
            if op is None:
                return

            # Clean up session to operation index.
            so = self._session_to_op_ids.get(op.session_id)
            if so is not None:
                so.discard(op_id)
                if not so:
                    del self._session_to_op_ids[op.session_id]

            # Cascade-remove all edges under this operation.
            for eid in list(self._op_to_edge_ids.pop(op_id, set())):
                self.remove_edge(eid)

    def get_operation(self, op_id: str) -> OpRecord | None:
        with self._lock:
            return self._operations.get(op_id)

    def add_session(self, session: Session) -> None:
        with self._lock:
            if session.session_id in self._sessions:
                raise ValueError(
                    f"Session '{session.session_id}' already exists in the graph. "
                    "Use `remove_session` before re-inserting."
                )
            
            self._sessions[session.session_id] = session

    def remove_session(self, session_id: str) -> None:
        with self._lock: 
            session = self._sessions.pop(session_id, None)
            if session is None:
                return

            # Cascade-remove operations (each cascades to its edges).
            # Note that some sessions may have no operations
            # because they are not connected to any other operations.
            # In this case, directly removing the set will raise `KeyError`.
            # Therefore, we pass a default set into `pop` method to avoid this.
            for op_id in list(self._session_to_op_ids.pop(session_id, set())):
                self.remove_operation(op_id)

            # Cascade-remove nodes (each cascades to remaining connected edges).
            for nid in list(self._session_to_node_ids.pop(session_id, set())):
                self.remove_node(nid)

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def all_nodes(self) -> list[Variable]:
        with self._lock:
            return list(self._nodes.values())

    def all_edges(self) -> list[OpEdge]:
        with self._lock:
            return list(self._edges.values())

    def all_operations(self) -> list[OpRecord]:
        with self._lock:
            return list(self._operations.values())

    def all_sessions(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def serialize(self) -> dict[str, Any]:
        with self._lock:
            return {
                "nodes": [n.model_dump() for n in self._nodes.values()],
                "edges": [e.model_dump() for e in self._edges.values()],
                "operations": [o.model_dump() for o in self._operations.values()],
                "sessions": [s.model_dump() for s in self._sessions.values()],
            }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> Self:
        driver = cls()
        for session_data in data.get("sessions", []):
            driver.add_session(Session.model_validate(session_data))
        for node_data in data.get("nodes", []):
            driver.add_node(Variable.model_validate(node_data))
        for op_data in data.get("operations", []):
            driver.add_operation(OpRecord.model_validate(op_data))
        for edge_data in data.get("edges", []):
            driver.add_edge(OpEdge.model_validate(edge_data))
        return driver
