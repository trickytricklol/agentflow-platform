import time

from agentflow.agents import AgentDefinition, AgentOrchestrator, AgentTask


def test_sub_agents_execute_in_parallel_and_aggregate():
    def worker(task):
        time.sleep(0.02)
        return task.input["value"] * 2

    orchestrator = AgentOrchestrator(max_workers=2)
    orchestrator.register(AgentDefinition("worker", "执行专项计算", worker))
    results = orchestrator.execute([("worker", AgentTask("b", "b", {"value": 2})), ("worker", AgentTask("a", "a", {"value": 1}))])
    assert [(item.task_id, item.value) for item in results] == [("a", 2), ("b", 4)]


def test_missing_agent_is_reported_not_raised():
    result = AgentOrchestrator().execute([("missing", AgentTask("x", "x"))])[0]
    assert result.success is False
    assert result.error == "agent not available"
