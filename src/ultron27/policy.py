from __future__ import annotations

from .models import Plan, PolicyDecision, RiskLevel, ValidationResult


BLOCKED_TOOL_NAMES = {
    "arbitrary_shell",
    "read_credentials",
    "disable_security",
    "exfiltrate_files",
}


def decide(plan: Plan, validation: ValidationResult, confirmed: bool = False) -> PolicyDecision:
    if not validation.valid:
        return PolicyDecision("block", "; ".join(validation.errors), RiskLevel.BLOCKED, True)

    if plan.tool_call.name in BLOCKED_TOOL_NAMES:
        return PolicyDecision("block", "This tool is explicitly blocked.", RiskLevel.BLOCKED, True)

    if plan.tool_call.name == "unsupported_request":
        return PolicyDecision("block", "No safe supported tool matched the request.", RiskLevel.NONE, False)

    if plan.risk_level == RiskLevel.HIGH and not confirmed:
        return PolicyDecision("confirm", "High-risk command requires confirmation.", plan.risk_level, True)

    if plan.requires_confirmation and not confirmed:
        return PolicyDecision("confirm", "This command requires confirmation before execution.", plan.risk_level, True)

    return PolicyDecision("allow", f"{plan.risk_level.value.capitalize()}-risk command can run.", plan.risk_level, plan.requires_confirmation)

