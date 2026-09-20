"""Small, dependency-free adapter for BFCL-style native function calls.

This scorer is intentionally named BFCL-style rather than official BFCL: the
official leaderboard owns additional parsing and AST evaluation behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any

from agentflow.providers import ChatMessage, ModelProvider, ModelResponse


@dataclass(frozen=True)
class BFCLCall:
    name: str
    arguments: dict[str, Any]


def _same_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(actual, str) and isinstance(expected, str):
        return " ".join(actual.strip().lower().split()) == " ".join(expected.strip().lower().split())
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_value(left, right) for left, right in zip(actual, expected))
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_value(actual[key], expected[key]) for key in actual)
    return actual == expected


def score_bfcl_call(call: BFCLCall | None, ground_truth: list[dict[str, dict[str, list[Any]]]]) -> bool:
    """Match one simple BFCL call against documented acceptable values."""
    if call is None:
        return False
    for alternative in ground_truth:
        if call.name not in alternative:
            continue
        expected_arguments = alternative[call.name]
        if set(call.arguments) - set(expected_arguments):
            continue
        valid = True
        for name, acceptable in expected_arguments.items():
            if name not in call.arguments:
                if "" not in acceptable:
                    valid = False
                    break
            elif not any(option != "" and _same_value(call.arguments[name], option) for option in acceptable):
                valid = False
                break
        if valid:
            return True
    return False


def _openai_tools(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools=[]
    for item in functions:
        function=json.loads(json.dumps(item))
        parameters=function.get("parameters", {})
        if parameters.get("type") == "dict":
            parameters["type"]="object"
        tools.append({"type":"function", "function":function})
    return tools


def _extract_call(response: ModelResponse) -> BFCLCall | None:
    choices=response.raw.get("choices", [])
    tool_calls=choices[0].get("message", {}).get("tool_calls", []) if choices else []
    if len(tool_calls) != 1:
        return None
    function=tool_calls[0].get("function", {})
    arguments=function.get("arguments", {})
    try:
        if isinstance(arguments, str):
            arguments=json.loads(arguments)
    except json.JSONDecodeError:
        return None
    if not isinstance(function.get("name"), str) or not isinstance(arguments, dict):
        return None
    return BFCLCall(function["name"], arguments)


def evaluate_bfcl_case(provider: ModelProvider, model: str, case: dict[str, Any], ground_truth: list[dict[str, Any]], system_prompt: str, seed: int) -> dict[str, Any]:
    question=case["question"][0]
    messages=[ChatMessage("system", system_prompt)]+[ChatMessage(item["role"], item["content"]) for item in question]
    response=provider.chat(messages, model=model, temperature=0.0, tools=_openai_tools(case["function"]), tool_choice="required", seed=seed, max_tokens=1024)
    call=_extract_call(response)
    return {
        "id":case["id"],
        "correct":score_bfcl_call(call, ground_truth),
        "call":None if call is None else {"name":call.name,"arguments":call.arguments},
        "input_tokens":response.input_tokens,
        "output_tokens":response.output_tokens,
        "raw":response.raw,
    }
