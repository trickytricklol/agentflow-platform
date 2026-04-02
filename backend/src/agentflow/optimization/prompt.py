from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PromptCandidate:
    prompt: str
    score: float | None = None
    evaluations: int = 0


@dataclass
class OptimizationExperiment:
    objective: str
    candidates: list[PromptCandidate] = field(default_factory=list)
    best: PromptCandidate | None = None
    history: list[PromptCandidate] = field(default_factory=list)


class PromptOptimizer:
    """Replaceable optimization loop; MVP uses optimistic candidate sampling."""

    def __init__(self, evaluator: Callable[[str], float]):
        self.evaluator = evaluator

    def run(self, experiment: OptimizationExperiment, rounds: int = 1) -> PromptCandidate:
        if not experiment.candidates:
            raise ValueError("at least one prompt candidate is required")
        for _ in range(max(1, rounds)):
            candidate = min(experiment.candidates, key=lambda item: item.evaluations)
            candidate.score = float(self.evaluator(candidate.prompt))
            candidate.evaluations += 1
            experiment.history.append(PromptCandidate(candidate.prompt, candidate.score, candidate.evaluations))
            if experiment.best is None or candidate.score > (experiment.best.score or float("-inf")):
                experiment.best = PromptCandidate(candidate.prompt, candidate.score, candidate.evaluations)
        return experiment.best
