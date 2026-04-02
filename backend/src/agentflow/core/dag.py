from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


class DagError(ValueError):
    """Raised when workflow DSL cannot form a valid DAG."""


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    when: str = "success"


class WorkflowGraph:
    """Validated workflow graph built from the platform DSL."""

    def __init__(self, nodes: dict[str, Node], edges: list[Edge]):
        self.nodes = nodes
        self.edges = edges
        self.parents: dict[str, list[str]] = defaultdict(list)
        self.children: dict[str, list[str]] = defaultdict(list)
        self._build_indexes()
        self._validate()

    @classmethod
    def from_dsl(cls, dsl: dict[str, Any]) -> "WorkflowGraph":
        if not isinstance(dsl, dict):
            raise DagError("DSL must be an object")
        raw_nodes = dsl.get("nodes", [])
        raw_edges = dsl.get("edges", [])
        nodes: dict[str, Node] = {}
        for raw in raw_nodes:
            node_id = raw.get("id") if isinstance(raw, dict) else None
            if not node_id:
                raise DagError("node id is required")
            if node_id in nodes:
                raise DagError(f"duplicate node id: {node_id}")
            nodes[node_id] = Node(node_id, raw.get("type", ""), raw.get("config", {}))
        edges = [Edge(e.get("source", ""), e.get("target", ""), e.get("when", "success")) for e in raw_edges]
        return cls(nodes, edges)

    def _build_indexes(self) -> None:
        for edge in self.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise DagError(f"edge references unknown node: {edge.source}->{edge.target}")
            self.parents[edge.target].append(edge.source)
            self.children[edge.source].append(edge.target)

    def _validate(self) -> None:
        starts = [n.id for n in self.nodes.values() if n.type == "start"]
        if len(starts) != 1:
            raise DagError(f"workflow must contain exactly one start node, got {len(starts)}")
        for node in self.nodes.values():
            if not node.type:
                raise DagError(f"node type is required: {node.id}")
        self.topological_order()
        reachable = set()
        queue = deque(starts)
        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            queue.extend(self.children[current])
        unreachable = set(self.nodes) - reachable
        if unreachable:
            raise DagError(f"unreachable nodes: {sorted(unreachable)}")

    def topological_order(self) -> list[str]:
        indegree = {node_id: len(self.parents[node_id]) for node_id in self.nodes}
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for child in self.children[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(order) != len(self.nodes):
            cycle = self._find_cycle()
            raise DagError(f"cycle detected: {' -> '.join(cycle)}")
        return order

    def _find_cycle(self) -> list[str]:
        visiting: set[str] = set()
        visited: set[str] = set()
        path: list[str] = []

        def visit(node_id: str) -> list[str] | None:
            visiting.add(node_id)
            path.append(node_id)
            for child in self.children[node_id]:
                if child in visiting:
                    return path[path.index(child):] + [child]
                if child not in visited:
                    found = visit(child)
                    if found:
                        return found
            path.pop()
            visiting.remove(node_id)
            visited.add(node_id)
            return None

        for node_id in self.nodes:
            if node_id not in visited:
                found = visit(node_id)
                if found:
                    return found
        return []


class DagExecutor:
    """Small synchronous executor used as the first engine milestone."""

    def __init__(self, graph: WorkflowGraph):
        self.graph = graph

    def run(self, handlers: dict[str, Callable[[Node, dict[str, Any]], Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
        values = dict(context or {})
        for node_id in self.graph.topological_order():
            node = self.graph.nodes[node_id]
            handler = handlers.get(node.type)
            if handler is None:
                raise DagError(f"no handler registered for node type: {node.type}")
            values[node_id] = handler(node, values)
        return values
