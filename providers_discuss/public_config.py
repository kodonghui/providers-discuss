from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .artifacts import (
    DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT,
    PROVIDER_SEATS_SCHEMA,
)
from .agent_profiles import DEFAULT_AGENT_PROFILE_PRESET, apply_agent_profiles_to_seats, validate_agent_profile_config
from .provider_adapters import SUPPORTED_REASONING_EFFORTS, validate_adapter_seat
from .profiles import (
    annotate_rounds_with_deliverable_profile,
    builtin_deliverable_profile,
    config_deliverable_profile,
    validate_deliverable_profile,
)


PUBLIC_CONFIG_SCHEMA = "providers-discuss.public-config.v1"
PUBLIC_CONFIG_VERIFY_SCHEMA = "providers-discuss.public-config.verify.v1"
SUPPORTED_TRANSPORTS = {
    "manual",
    "codex_exec_file",
    "claude_k",
    "claude_k_team_agents",
    "gemini_cli",
}
SUPPORTED_PROVIDERS = {
    "anthropic",
    "google",
    "manual",
    "openai",
    "other",
}


def example_public_config() -> dict[str, Any]:
    return {
        "schema": PUBLIC_CONFIG_SCHEMA,
        "language": {
            "conversation": "English",
            "supported": ["English", "Korean", "Chinese", "Japanese", "Spanish"],
        },
        "objective": "Replace this with the provider discussion objective.",
        "brainstorming": {
            "mode": "none",
            "include_as_provider_input": True,
        },
        "input": {
            "source_dirs": ["./inputs"],
            "package_strategy": "orchestrator_reads_sources_and_builds_input_pack",
        },
        "orchestrator": {
            "read_prior_rounds": True,
            "write_prompt_delta_after_each_round": True,
            "claim_gate_required": True,
        },
        "deliverable_profile": builtin_deliverable_profile("development_contract"),
        "agent_profile_defaults": {
            "enabled": False,
            "preset": DEFAULT_AGENT_PROFILE_PRESET,
        },
        "rounds": [
            {"round_id": "R1", "mode": "explore", "title": "Independent proposals and risk candidates"},
            {"round_id": "R2", "mode": "challenge", "title": "Challenge unsupported claims and hidden assumptions"},
            {"round_id": "R3", "mode": "decide", "title": "Decision contract and implementation gate"},
        ],
        "seats": [
            {
                "seat_id": "gpt_coder",
                "provider": "openai",
                "transport": "codex_exec_file",
                "model": "gpt-5.5",
                "reasoning_effort": "high",
                "role": "skeptic, verifier, overengineering check",
                "required": True,
                "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
                "execution": {
                    "sandbox": "workspace-write",
                    "answer_path_required": True,
                    "stdout_capture_fallback": True,
                    "completion_marker": "KDH_CODEX_DONE",
                    "read_only_sandbox_forbidden": True,
                },
            },
            {
                "seat_id": "claude_team",
                "provider": "anthropic",
                "transport": "claude_k_team_agents",
                "model": "opus",
                "reasoning_effort": "max",
                "role": "team-based source reading, critique, recorder",
                "required": True,
                "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
                "execution": {
                    "model": "opus",
                    "effort": "max",
                    "permission_mode": "auto",
                },
                "team_agents": {
                    "enabled": True,
                    "roles": ["source-reader", "skeptic", "recorder"],
                    "required_direct_message_count": DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT,
                },
            },
            {
                "seat_id": "gemini_optional",
                "provider": "google",
                "transport": "gemini_cli",
                "model": "auto",
                "reasoning_effort": "default",
                "role": "optional third opinion and contradiction finder",
                "required": False,
                "enabled": False,
                "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
            },
        ],
    }


def read_public_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("public config root must be an object")
    return data


def validate_public_config(data: dict[str, Any], *, config_path: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []

    _check(checks, blockers, "schema", data.get("schema") == PUBLIC_CONFIG_SCHEMA, f"expected {PUBLIC_CONFIG_SCHEMA}")
    objective = str(data.get("objective") or "").strip()
    _check(checks, blockers, "objective_present", bool(objective), "objective is required")

    rounds = data.get("rounds")
    _check(checks, blockers, "rounds_array", isinstance(rounds, list) and bool(rounds), "rounds must be a non-empty array")
    if isinstance(rounds, list):
        _validate_rounds(rounds, checks, blockers)

    seats = data.get("seats")
    _check(checks, blockers, "seats_array", isinstance(seats, list) and bool(seats), "seats must be a non-empty array")
    if isinstance(seats, list):
        _validate_seats(seats, checks, blockers)

    try:
        deliverable_profile = config_deliverable_profile(data)
        for blocker in validate_deliverable_profile(deliverable_profile):
            _check(checks, blockers, blocker["check"], False, blocker["reason"])
    except ValueError as exc:
        _check(checks, blockers, "deliverable_profile", False, str(exc))

    for blocker in validate_agent_profile_config(data, config_path=config_path):
        _check(checks, blockers, blocker["check"], False, blocker["reason"])

    status = "pass" if not blockers else "fail"
    return {
        "schema": PUBLIC_CONFIG_VERIFY_SCHEMA,
        "status": status,
        "checks": checks,
        "blockers": blockers,
    }


def rounds_from_public_config(data: dict[str, Any]) -> list[dict[str, str]]:
    rounds = []
    for item in data.get("rounds", []):
        rounds.append(
            {
                "round_id": str(item["round_id"]),
                "mode": str(item.get("mode") or "custom"),
                "title": str(item.get("title") or item["round_id"]),
            }
        )
    return annotate_rounds_with_deliverable_profile(rounds, config_deliverable_profile(data))


def provider_seats_from_public_config(
    data: dict[str, Any],
    *,
    config_path: Path | None = None,
    include_disabled: bool = False,
) -> dict[str, Any]:
    seats = []
    for seat in data.get("seats", []):
        if not include_disabled and seat.get("enabled", True) is False:
            continue
        normalized = _normalize_seat(seat)
        if include_disabled and seat.get("enabled", True) is False:
            normalized["enabled"] = False
        seats.append(normalized)
    apply_agent_profiles_to_seats(seats, data.get("agent_catalogs"), config_path=config_path, defaults=data.get("agent_profile_defaults"))
    return {
        "schema": PROVIDER_SEATS_SCHEMA,
        "topology": "dynamic",
        "preset": "custom",
        "seats": seats,
    }


def _validate_rounds(rounds: list[Any], checks: list[dict[str, Any]], blockers: list[dict[str, str]]) -> None:
    ids: list[str] = []
    for index, item in enumerate(rounds, start=1):
        if not isinstance(item, dict):
            blockers.append({"check": "round_object", "reason": f"round #{index} must be an object"})
            continue
        round_id = str(item.get("round_id") or "")
        ids.append(round_id)
        valid_id = bool(re.fullmatch(r"R[1-9][0-9]*", round_id))
        _check(checks, blockers, f"round_{index}_id", valid_id, f"invalid round_id: {round_id}")
        _check(checks, blockers, f"round_{index}_title", bool(str(item.get("title") or "").strip()), "round title is required")
    duplicates = sorted({item for item in ids if ids.count(item) > 1 and item})
    _check(checks, blockers, "round_ids_unique", not duplicates, f"duplicate round ids: {duplicates}")


def _validate_seats(seats: list[Any], checks: list[dict[str, Any]], blockers: list[dict[str, str]]) -> None:
    ids: list[str] = []
    enabled_required_count = 0
    for index, item in enumerate(seats, start=1):
        if not isinstance(item, dict):
            blockers.append({"check": "seat_object", "reason": f"seat #{index} must be an object"})
            continue
        seat_id = str(item.get("seat_id") or "")
        ids.append(seat_id)
        provider = str(item.get("provider") or "")
        transport = str(item.get("transport") or "")
        enabled = item.get("enabled", True) is not False
        required = item.get("required", True) is not False
        if enabled and required:
            enabled_required_count += 1
        _check(checks, blockers, f"seat_{index}_id", bool(re.fullmatch(r"[A-Za-z0-9_-]+", seat_id)), f"invalid seat_id: {seat_id}")
        _check(checks, blockers, f"seat_{index}_provider", provider in SUPPORTED_PROVIDERS, f"unsupported provider: {provider}")
        _check(checks, blockers, f"seat_{index}_transport", transport in SUPPORTED_TRANSPORTS, f"unsupported transport: {transport}")
        _check(checks, blockers, f"seat_{index}_role", bool(str(item.get("role") or "").strip()), "seat role is required")
        timeout = item.get("timeout_seconds", DEFAULT_PROVIDER_TIMEOUT_SECONDS)
        _check(checks, blockers, f"seat_{index}_timeout", isinstance(timeout, int) and timeout > 0, "timeout_seconds must be a positive integer")
        execution_for_effort = item.get("execution") if isinstance(item.get("execution"), dict) else {}
        effort = str(item.get("reasoning_effort") or execution_for_effort.get("effort") or "default")
        _check(checks, blockers, f"seat_{index}_reasoning_effort", effort in SUPPORTED_REASONING_EFFORTS, f"unsupported reasoning_effort: {effort}")
        for adapter_blocker in validate_adapter_seat(item):
            _check(checks, blockers, f"seat_{index}_{adapter_blocker['check']}", False, adapter_blocker["reason"])
        if transport == "codex_exec_file":
            execution = item.get("execution") if isinstance(item.get("execution"), dict) else {}
            _check(checks, blockers, f"seat_{index}_codex_writable", execution.get("sandbox") != "read-only", "codex_exec_file must not be read-only")
            _check(
                checks,
                blockers,
                f"seat_{index}_codex_answer_contract",
                execution.get("answer_path_required") is True and execution.get("stdout_capture_fallback") is True,
                "codex_exec_file needs answer_path_required and stdout_capture_fallback",
            )
        if transport == "claude_k_team_agents":
            team_agents = item.get("team_agents") or {}
            roles = team_agents.get("roles") or team_agents.get("required_teammates") or []
            _check(checks, blockers, f"seat_{index}_team_agents_enabled", team_agents.get("enabled") is True, "team_agents.enabled must be true")
            valid_roles = isinstance(roles, list) and len(roles) >= 2 and all(isinstance(role, (str, dict)) for role in roles)
            _check(checks, blockers, f"seat_{index}_team_roles", valid_roles, "Team Agents roles must contain at least two string or object roles")
    duplicates = sorted({item for item in ids if ids.count(item) > 1 and item})
    _check(checks, blockers, "seat_ids_unique", not duplicates, f"duplicate seat ids: {duplicates}")
    _check(checks, blockers, "enabled_required_seat_present", enabled_required_count > 0, "at least one enabled required seat is needed")


def _normalize_seat(seat: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(seat)
    normalized.pop("enabled", None)
    normalized.setdefault("required", True)
    normalized.setdefault("timeout_seconds", DEFAULT_PROVIDER_TIMEOUT_SECONDS)
    execution = dict(normalized.get("execution") or {})
    if normalized.get("model") and "model" not in execution:
        execution["model"] = normalized["model"]
    if normalized.get("reasoning_effort") and "effort" not in execution:
        execution["effort"] = normalized["reasoning_effort"]
    if normalized.get("transport") == "codex_exec_file":
        execution.setdefault("sandbox", "workspace-write")
        execution.setdefault("answer_path_required", True)
        execution.setdefault("stdout_capture_fallback", True)
        execution.setdefault("completion_marker", "KDH_CODEX_DONE")
        execution.setdefault("read_only_sandbox_forbidden", True)
    if execution:
        normalized["execution"] = execution
    if normalized.get("transport") == "claude_k_team_agents":
        team_agents = dict(normalized.get("team_agents") or {})
        roles = team_agents.get("roles") or team_agents.get("required_teammates") or ["source-reader", "skeptic", "recorder"]
        team_agents["enabled"] = True
        team_agents["roles"] = list(roles)
        team_agents["required_teammates"] = [_role_name(role) for role in roles]
        team_agents.setdefault("required_direct_message_count", DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT)
        normalized["team_agents"] = team_agents
    return normalized


def _role_name(role: Any) -> str:
    if isinstance(role, dict):
        return str(role.get("name") or role.get("role") or role.get("agent_profile_id") or "").strip()
    return str(role).strip()


def _check(
    checks: list[dict[str, Any]],
    blockers: list[dict[str, str]],
    name: str,
    passed: bool,
    reason: str,
) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail", **({} if passed else {"reason": reason})})
    if not passed:
        blockers.append({"check": name, "reason": reason})
