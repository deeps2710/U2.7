from __future__ import annotations

from .models import Plan, PolicyDecision, RiskLevel, ValidationResult


BLOCKED_TOOL_NAMES = {
    "arbitrary_shell",
    "read_credentials",
    "disable_security",
    "exfiltrate_files",
}

DESTRUCTIVE_OR_UNIMPLEMENTED_TOOLS = {
    "delete_file",
    "move_file",
    "rename_file",
    "restart_system",
    "run_script",
    "send_email",
    "shutdown_system",
}


def decide(plan: Plan, validation: ValidationResult, confirmed: bool = False) -> PolicyDecision:
    permission_level = _permission_level(plan.risk_level, plan.tool_call.name)
    if not validation.valid:
        return PolicyDecision("block", "; ".join(validation.errors), RiskLevel.BLOCKED, True, "blocked")

    if plan.tool_call.name in BLOCKED_TOOL_NAMES:
        return PolicyDecision("block", "This tool is explicitly blocked.", RiskLevel.BLOCKED, True, "blocked")

    if plan.tool_call.name == "unsupported_request":
        return PolicyDecision("block", "No safe supported tool matched the request.", RiskLevel.NONE, False, "no_execution")

    if plan.risk_level == RiskLevel.HIGH and not confirmed:
        return PolicyDecision("confirm", "High-risk command requires confirmation.", plan.risk_level, True, permission_level)

    if plan.risk_level == RiskLevel.MEDIUM and not confirmed:
        return PolicyDecision("confirm", "Medium-risk command requires confirmation.", plan.risk_level, True, permission_level)

    if plan.requires_confirmation and not confirmed:
        return PolicyDecision("confirm", "This command requires confirmation before execution.", plan.risk_level, True, permission_level)

    return PolicyDecision(
        "allow",
        f"{plan.risk_level.value.capitalize()}-risk command can run.",
        plan.risk_level,
        plan.requires_confirmation or plan.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH},
        permission_level,
    )


def _permission_level(risk_level: RiskLevel, tool_name: str) -> str:
    if tool_name in DESTRUCTIVE_OR_UNIMPLEMENTED_TOOLS:
        return "destructive_blocked_or_not_implemented"
    if risk_level == RiskLevel.LOW:
        return "low_risk_allowed"
    if risk_level == RiskLevel.MEDIUM:
        return "medium_risk_confirmation"
    if risk_level == RiskLevel.HIGH:
        return "high_risk_confirmation"
    if risk_level == RiskLevel.BLOCKED:
        return "blocked"
    return "no_execution"
