from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


PolicyAction = Literal["allow", "confirm", "block"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk_level: RiskLevel
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    requires_confirmation: bool = False
    numeric_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    utterance: str
    intent: str
    tool_call: ToolCall
    risk_level: RiskLevel
    requires_confirmation: bool
    source: str
    confidence: float


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    reason: str
    risk_level: RiskLevel
    requires_confirmation: bool
    permission_level: str = ""


@dataclass(frozen=True)
class ToolResult:
    status: str
    message: str
    changed: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
