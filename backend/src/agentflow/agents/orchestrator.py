from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentDefinition:
    name: str
    description: str
    handler: Callable[["AgentTask"], Any]
    enabled: bool = True


@dataclass
class AgentTask:
    id: str
    instruction: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    agent: str
    success: bool
    value: Any = None
    error: str | None = None


class AgentOrchestrator:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        if not agent.name or not agent.description:
            raise ValueError("agent name and description are required")
        self._agents[agent.name] = agent

    def list_agents(self) -> list[AgentDefinition]:
        return [agent for agent in self._agents.values() if agent.enabled]

    def execute(self, assignments: list[tuple[str, AgentTask]], *, fail_fast: bool = False) -> list[TaskResult]:
        results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._run_one, agent_name, task): (agent_name, task) for agent_name, task in assignments}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if fail_fast and not result.success:
                    for pending in futures:
                        pending.cancel()
                    break
        return sorted(results, key=lambda item: item.task_id)

    def _run_one(self, agent_name: str, task: AgentTask) -> TaskResult:
        agent = self._agents.get(agent_name)
        if agent is None or not agent.enabled:
            return TaskResult(task.id, agent_name, False, error="agent not available")
        try:
            return TaskResult(task.id, agent_name, True, value=agent.handler(task))
        except Exception as exc:
            return TaskResult(task.id, agent_name, False, error=str(exc))
