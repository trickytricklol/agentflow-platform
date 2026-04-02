from __future__ import annotations

import json
import math
import re
from urllib.request import Request, urlopen
from typing import Any


class EmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class TfidfEmbedding(EmbeddingProvider):
    """Dependency-free lexical embedding used for offline MVP experiments."""

    def __init__(self, corpus: list[str] | None = None):
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        if corpus:
            self.fit(corpus)

    def fit(self, corpus: list[str]) -> None:
        documents = [self._tokens(text) for text in corpus]
        terms = sorted({term for document in documents for term in document})
        self.vocabulary = {term: index for index, term in enumerate(terms)}
        count = len(documents)
        self.idf = {term: math.log((1 + count) / (1 + sum(term in document for document in documents))) + 1 for term in terms}

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * len(self.vocabulary)
        tokens = self._tokens(text)
        for token in tokens:
            if token in self.vocabulary:
                vector[self.vocabulary[token]] += self.idf.get(token, 1.0)
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        words = set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
        words.update(chinese[index:index + 2] for index in range(len(chinese) - 1))
        return words


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        request = Request(self.base_url + "/api/embed", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=60) as response:
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        embeddings = data.get("embeddings") or [data["embedding"]]
        return embeddings[0]
