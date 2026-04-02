from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import ModelProvider


@dataclass
class ModelConfig:
    name: str
    provider: str
    model: str
    base_url: str = ""
    enabled: bool = True


class ModelRegistry:
    def __init__(self):
        self._configs: dict[str, ModelConfig] = {}
        self._providers: dict[str, ModelProvider] = {}

    def register(self, config: ModelConfig, provider: ModelProvider) -> None:
        self._configs[config.name] = config
        self._providers[config.name] = provider

    def get(self, name: str) -> tuple[ModelConfig, ModelProvider]:
        config = self._configs.get(name)
        provider = self._providers.get(name)
        if not config or not provider or not config.enabled:
            raise KeyError(f"model not available: {name}")
        return config, provider

    def list(self) -> list[dict[str, Any]]:
        return [{"name": c.name, "provider": c.provider, "model": c.model, "base_url": c.base_url, "enabled": c.enabled} for c in self._configs.values()]
