import pytest

from agentflow.tools import ToolDefinition, ToolRouter, ToolValidationError


def test_tool_arguments_validate_required_types_and_unknown_fields():
    tool = ToolDefinition("weather", "weather", lambda city: city, {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]})
    assert ToolRouter.validate_arguments(tool, {"city": "Shanghai"})["city"] == "Shanghai"
    with pytest.raises(ToolValidationError):
        ToolRouter.validate_arguments(tool, {})
    with pytest.raises(ToolValidationError):
        ToolRouter.validate_arguments(tool, {"city": 123})
    with pytest.raises(ToolValidationError):
        ToolRouter.validate_arguments(tool, {"city": "Shanghai", "extra": 1})
