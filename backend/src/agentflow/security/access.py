from __future__ import annotations

from dataclasses import dataclass, field
import hmac


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: set[str] = field(default_factory=set)


@dataclass
class AuthConfig:
    enabled: bool = False
    tokens: dict[str, Principal] = field(default_factory=dict)

    def authenticate(self, authorization: str | None) -> Principal:
        if not self.enabled:
            return Principal("development", {"admin"})
        if not authorization or not authorization.startswith("Bearer "):
            raise PermissionError("Bearer token required")
        supplied = authorization[7:]
        principal = None
        for token, candidate in self.tokens.items():
            if hmac.compare_digest(token, supplied):
                principal = candidate
        if principal is None:
            raise PermissionError("invalid token")
        return principal


def authorize(principal: Principal, role: str) -> None:
    if role not in principal.roles and "admin" not in principal.roles:
        raise PermissionError(f"role required: {role}")
