from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from .embeddings import EmbeddingProvider


@dataclass
class BayesianObservation:
    prompt: str
    score: float


@dataclass
class BayesianExperiment:
    observations: list[BayesianObservation] = field(default_factory=list)


class GaussianProcessOptimizer:
    """Small dependency-free GP + Expected Improvement optimizer."""

    def __init__(self, embedding: EmbeddingProvider, noise: float = 0.05, length_scale: float = 1.0):
        self.embedding = embedding
        self.noise = noise
        self.length_scale = length_scale

    def run(self, candidates: list[str], evaluator: Callable[[str], float], rounds: int, experiment: BayesianExperiment | None = None) -> BayesianExperiment:
        experiment = experiment or BayesianExperiment()
        vectors = {candidate: self.embedding.embed(candidate) for candidate in candidates}
        for _ in range(min(rounds, len(candidates))):
            remaining = [candidate for candidate in candidates if candidate not in {item.prompt for item in experiment.observations}]
            if not remaining:
                break
            selected = remaining[0] if not experiment.observations else max(remaining, key=lambda item: self._expected_improvement(vectors[item], experiment, vectors))
            experiment.observations.append(BayesianObservation(selected, float(evaluator(selected))))
        return experiment

    def _expected_improvement(self, vector: list[float], experiment: BayesianExperiment, vectors: dict[str, list[float]]) -> float:
        observations = experiment.observations
        if not observations:
            return 1.0
        mean, variance = self.posterior(vector, experiment, vectors)
        sigma = math.sqrt(variance)
        improvement = mean - max(item.score for item in observations)
        z = improvement / sigma
        normal_cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        normal_pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        return improvement * normal_cdf + sigma * normal_pdf

    def posterior(self, vector: list[float], experiment: BayesianExperiment, vectors: dict[str, list[float]]) -> tuple[float,float]:
        """Return GP posterior mean and variance for auditable constrained acquisition."""
        observations=experiment.observations
        if not observations:
            return 0.0,self._kernel(vector,vector)
        matrix = [[self._kernel(vectors[left.prompt], vectors[right.prompt]) + (self.noise if index == jndex else 0.0) for jndex, right in enumerate(observations)] for index, left in enumerate(observations)]
        target = [self._kernel(vector, vectors[item.prompt]) for item in observations]
        alpha = self._solve(matrix, [item.score for item in observations])
        mean = sum(weight * value for weight, value in zip(target, alpha))
        variance = max(1e-9, self._kernel(vector, vector) - sum(weight * value for weight, value in zip(target, self._solve(matrix, target))))
        return mean,variance

    def _kernel(self, left: list[float], right: list[float]) -> float:
        distance = sum((a - b) ** 2 for a, b in zip(left, right))
        return math.exp(-distance / (2 * self.length_scale ** 2))

    @staticmethod
    def _solve(matrix: list[list[float]], values: list[float]) -> list[float]:
        augmented = [row[:] + [value] for row, value in zip(matrix, values)]
        for pivot in range(len(augmented)):
            best = max(range(pivot, len(augmented)), key=lambda row: abs(augmented[row][pivot]))
            augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
            divisor = augmented[pivot][pivot] or 1e-9
            augmented[pivot] = [value / divisor for value in augmented[pivot]]
            for row in range(len(augmented)):
                if row == pivot:
                    continue
                factor = augmented[row][pivot]
                augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[pivot])]
        return [row[-1] for row in augmented]
