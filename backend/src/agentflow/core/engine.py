from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

from .dag import Node, WorkflowGraph


class NodeStatus(str, Enum):
    INIT = "INIT"
    MARK = "MARK"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass
class NodeResult:
    value: Any = None
    success: bool = True
    error: str | None = None


@dataclass
class NodeState:
    node_id: str
    status: NodeStatus = NodeStatus.INIT
    value: Any = None
    error: str | None = None
    attempts: int = 0


@dataclass(frozen=True)
class EngineEvent:
    node_id: str
    status: NodeStatus
    attempt: int = 0
    error: str | None = None


@dataclass
class RunResult:
    status: NodeStatus
    nodes: dict[str, NodeState]
    events: list[EngineEvent] = field(default_factory=list)


Handler = Any


class WorkflowEngine:
    """Deterministic first-version workflow engine built on a validated DAG."""

    def __init__(self, graph: WorkflowGraph, handlers: dict[str, Handler], max_retries: int = 0):
        self.graph = graph
        self.handlers = handlers
        self.max_retries = max(0, max_retries)

    def run(self, context: dict[str, Any] | None = None) -> RunResult:
        states = {node_id: NodeState(node_id) for node_id in self.graph.nodes}
        events: list[EngineEvent] = []
        values = dict(context or {})
        for node_id in self.graph.topological_order():
            state = states[node_id]
            node = self.graph.nodes[node_id]
            if self.graph.parents[node_id] and not self._is_activated(node_id, states):
                self._transition(state, NodeStatus.MARK, events)
                self._transition(state, NodeStatus.SKIP, events)
                continue
            self._transition(state, NodeStatus.MARK, events)
            handler = self.handlers.get(node.type)
            if handler is None:
                self._fail(state, events, f"no handler registered for node type: {node.type}")
                continue
            while True:
                state.attempts += 1
                self._transition(state, NodeStatus.RUNNING, events, state.attempts)
                try:
                    raw = handler(node, values)
                    result = raw if isinstance(raw, NodeResult) else NodeResult(raw)
                except Exception as exc:
                    result = NodeResult(success=False, error=str(exc))
                if result.success:
                    state.value = result.value
                    values[node_id] = result.value
                    self._transition(state, NodeStatus.SUCCESS, events, state.attempts)
                    break
                if state.attempts > self.max_retries:
                    self._fail(state, events, result.error or "node execution failed", state.attempts)
                    break
        failed = any(state.status == NodeStatus.ERROR for state in states.values())
        return RunResult(NodeStatus.ERROR if failed else NodeStatus.SUCCESS, states, events)

    def run_parallel(self, context: dict[str, Any] | None = None, max_workers: int = 4, timeout_seconds: float | None = None, cancel_event: Event | None = None) -> RunResult:
        """Execute independent nodes in the same DAG layer concurrently."""
        states = {node_id: NodeState(node_id) for node_id in self.graph.nodes}
        values = dict(context or {})
        events: list[EngineEvent] = []
        pending = set(self.graph.nodes)
        timed_out: set[str] = set()

        while pending:
            if cancel_event and cancel_event.is_set():
                for node_id in pending:
                    states[node_id].status = NodeStatus.SKIP
                    events.append(EngineEvent(node_id, NodeStatus.SKIP))
                break
            ready = [node_id for node_id in pending if all(parent not in pending for parent in self.graph.parents[node_id])]
            if not ready:
                raise RuntimeError("parallel scheduler stalled")
            snapshot = dict(values)

            def execute(node_id: str):
                state = states[node_id]
                node = self.graph.nodes[node_id]
                local_events: list[EngineEvent] = []
                if self.graph.parents[node_id] and not self._is_activated(node_id, states):
                    self._transition(state, NodeStatus.MARK, local_events)
                    self._transition(state, NodeStatus.SKIP, local_events)
                    return node_id, state, None, local_events
                self._transition(state, NodeStatus.MARK, local_events)
                handler = self.handlers.get(node.type)
                if handler is None:
                    self._fail(state, local_events, f"no handler registered for node type: {node.type}")
                    return node_id, state, None, local_events
                while True:
                    state.attempts += 1
                    self._transition(state, NodeStatus.RUNNING, local_events, state.attempts)
                    try:
                        raw = handler(node, snapshot)
                        result = raw if isinstance(raw, NodeResult) else NodeResult(raw)
                    except Exception as exc:
                        result = NodeResult(success=False, error=str(exc))
                    if result.success:
                        if node_id in timed_out:
                            return node_id, state, None, local_events
                        state.value = result.value
                        self._transition(state, NodeStatus.SUCCESS, local_events, state.attempts)
                        return node_id, state, result.value, local_events
                    if state.attempts > self.max_retries:
                        self._fail(state, local_events, result.error or "node execution failed", state.attempts)
                        return node_id, state, None, local_events

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(execute, node_id) for node_id in ready]
                results = []
                for node_id, future in zip(ready, futures):
                    try:
                        results.append(future.result(timeout=timeout_seconds))
                    except TimeoutError:
                        timed_out.add(node_id)
                        for pending_future in futures:
                            pending_future.cancel()
                        states[node_id].error = "node execution timeout"
                        states[node_id].status = NodeStatus.ERROR
                        results.append((node_id, states[node_id], None, [EngineEvent(node_id, NodeStatus.ERROR, error="node execution timeout")]))
            for node_id, state, value, local_events in results:
                pending.remove(node_id)
                events.extend(local_events)
                if state.status == NodeStatus.SUCCESS:
                    values[node_id] = value
        failed = any(state.status == NodeStatus.ERROR for state in states.values())
        return RunResult(NodeStatus.ERROR if failed else NodeStatus.SUCCESS, states, events)

    def _is_activated(self, node_id: str, states: dict[str, NodeState]) -> bool:
        edges = [edge for edge in self.graph.edges if edge.target == node_id]
        selected_sources = set()
        for edge in edges:
            parent_status = states[edge.source].status
            if edge.when in ("always", "*") or (edge.when == "success" and parent_status == NodeStatus.SUCCESS) or (edge.when == "fail" and parent_status == NodeStatus.ERROR):
                selected_sources.add(edge.source)
        if not selected_sources:
            return False
        return all(states[parent].status in (NodeStatus.SUCCESS, NodeStatus.ERROR, NodeStatus.SKIP) for parent in selected_sources)

    @staticmethod
    def _transition(state: NodeState, status: NodeStatus, events: list[EngineEvent], attempt: int = 0) -> None:
        state.status = status
        events.append(EngineEvent(state.node_id, status, attempt))

    def _fail(self, state: NodeState, events: list[EngineEvent], error: str, attempt: int = 0) -> None:
        state.error = error
        self._transition(state, NodeStatus.ERROR, events, attempt)
