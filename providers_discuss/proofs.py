from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TRANSPORT_PROOF_SCHEMA = "kdh.providers-discuss.transport-proof.v1"
TEAM_AGENTS_PROOF_SCHEMA = "kdh.providers-discuss.team-agents-proof.v1"
TEAM_AGENTS_TRIGGER_MODES = {"prompt_only", "providers_discuss_hook", "global_hook", "legacy_unspecified"}


def validate_transport_proof(proof: dict[str, Any], base: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    _expect(checks, blockers, "transport_schema", proof.get("schema") == TRANSPORT_PROOF_SCHEMA, "unexpected transport proof schema")

    transport = proof.get("transport")
    _expect(checks, blockers, "transport_supported", transport in {"codex_exec_file", "claude_k", "gemini_cli"}, f"unsupported transport: {transport}")
    _expect(checks, blockers, "not_timed_out", proof.get("timed_out") is not True, "transport timed out")
    _expect(checks, blockers, "not_killed_before_completion", proof.get("killed") is not True, "transport was killed before completion")
    _expect(checks, blockers, "not_blocked_by_runtime_prompt", not proof.get("blocked_reason"), str(proof.get("blocked_reason") or "runtime prompt blocked"))

    exit_code = proof.get("exit_code")
    if exit_code is not None:
        _expect(checks, blockers, "exit_code_zero", exit_code == 0, f"non-zero exit code: {exit_code}")

    if transport == "codex_exec_file":
        _validate_file_output(proof, base, checks, blockers, "answer_path")
    elif transport == "claude_k":
        _validate_claude_k(proof, base, checks, blockers)
    elif transport == "gemini_cli":
        _validate_gemini_cli(proof, base, checks, blockers)

    return _result(checks, blockers)


def validate_team_agents_proof(proof: dict[str, Any], base: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    _expect(checks, blockers, "team_agents_schema", proof.get("schema") == TEAM_AGENTS_PROOF_SCHEMA, "unexpected Team Agents proof schema")
    trigger_mode = str(proof.get("trigger_mode") or "legacy_unspecified")
    _expect(
        checks,
        blockers,
        "trigger_mode_classified",
        trigger_mode in TEAM_AGENTS_TRIGGER_MODES,
        f"unsupported trigger_mode: {trigger_mode}",
    )
    _expect(checks, blockers, "not_blocked_by_runtime_prompt", not proof.get("blocked_reason"), str(proof.get("blocked_reason") or "runtime prompt blocked"))
    _expect(checks, blockers, "team_create_observed", proof.get("team_create_used") is True, "TeamCreate not observed")
    _expect(checks, blockers, "team_identity_recorded", bool(proof.get("team_name") or proof.get("team_session_id")), "team identity missing")

    required_tasks = int(proof.get("required_task_count", 1))
    required_agents = int(proof.get("required_team_scoped_agent_calls", 1))
    required_messages = int(proof.get("direct_teammate_messages_required", 3))
    _expect(
        checks,
        blockers,
        "teammate_tasks_created",
        int(proof.get("task_create_count", 0)) >= required_tasks,
        f"task_create_count below {required_tasks}",
    )
    _expect(
        checks,
        blockers,
        "team_scoped_agents_used",
        int(proof.get("agent_calls_with_team_name", 0)) >= required_agents,
        f"team-scoped Agent count below {required_agents}",
    )
    _expect(
        checks,
        blockers,
        "direct_messages_observed",
        int(proof.get("direct_teammate_messages_observed", 0)) >= required_messages,
        f"direct teammate messages below {required_messages}",
    )
    _expect(checks, blockers, "ordinary_delegation_false", proof.get("ordinary_agent_delegation_only") is False, "ordinary delegation only")
    _expect(checks, blockers, "summary_only_false", proof.get("summary_only_delegation") is False, "summary-only delegation")

    artifacts = proof.get("artifacts", {})
    status_path = _expect_artifact(checks, blockers, base, artifacts.get("status"), "status_artifact_exists")
    if status_path and status_path.suffix == ".json":
        try:
            json.loads(status_path.read_text(encoding="utf-8"))
            _expect(checks, blockers, "status_artifact_json_parseable", True, "")
        except json.JSONDecodeError as exc:
            _expect(checks, blockers, "status_artifact_json_parseable", False, f"malformed status artifact JSON: {exc}")

    transcript_path = _expect_artifact(checks, blockers, base, artifacts.get("transcript"), "transcript_artifact_exists")
    session_jsonl = artifacts.get("session_jsonl", [])
    _expect(checks, blockers, "session_jsonl_listed", bool(session_jsonl), "session jsonl artifacts missing")
    session_paths: list[Path] = []
    for index, rel in enumerate(session_jsonl):
        path = _expect_artifact(checks, blockers, base, rel, f"session_jsonl_{index}_exists")
        if path:
            session_paths.append(path)
    team_state = artifacts.get("team_state", [])
    team_state_paths: list[Path] = []
    for index, rel in enumerate(team_state):
        path = _expect_artifact(checks, blockers, base, rel, f"team_state_{index}_exists")
        if path:
            team_state_paths.append(path)

    raw_transcript = _read_text(transcript_path)
    raw_session = "\n".join(_read_text(path) for path in session_paths)
    raw_all = "\n".join(item for item in (raw_transcript, raw_session) if item)
    team_name = str(proof.get("team_name") or proof.get("team_session_id") or "")
    session_tool_counts = _session_tool_counts(session_paths, team_name)
    _expect(
        checks,
        blockers,
        "team_state_or_equivalent_recorded",
        bool(team_state_paths) or session_tool_counts["team_state_equivalent"] >= 1,
        "team state artifact or TeamCreate result missing",
    )

    team_create_markers = _marker_list(proof, "team_create_markers", ["TeamCreate"])
    _expect(
        checks,
        blockers,
        "raw_team_create_marker",
        _contains_any(raw_transcript, team_create_markers) or session_tool_counts["team_create"] >= 1,
        f"raw transcript/session JSONL missing team creation marker: {team_create_markers}",
    )
    team_agent_count = max(_count_team_scoped_agent_markers(raw_all, team_name), session_tool_counts["agent_with_team_name"])
    _expect(
        checks,
        blockers,
        "raw_team_scoped_agent_markers",
        team_agent_count >= required_agents,
        f"raw transcript/session JSONL team-scoped Agent markers below {required_agents}: {team_agent_count}",
    )
    direct_message_markers = _marker_list(proof, "direct_message_markers", ["SendMessage"])
    direct_message_count = max(_count_marker_lines(raw_all, direct_message_markers), session_tool_counts["send_message"])
    _expect(
        checks,
        blockers,
        "raw_direct_message_markers",
        direct_message_count >= required_messages,
        f"raw direct-message markers below {required_messages}: {direct_message_count}",
    )
    _expect(
        checks,
        blockers,
        "session_team_create_tool_use",
        session_tool_counts["team_create"] >= 1,
        f"session JSONL TeamCreate tool_use missing: {session_tool_counts['team_create']}",
    )
    _expect(
        checks,
        blockers,
        "session_task_create_tool_uses",
        session_tool_counts["task_create"] >= required_tasks,
        f"session JSONL TaskCreate tool_use count below {required_tasks}: {session_tool_counts['task_create']}",
    )
    _expect(
        checks,
        blockers,
        "session_team_scoped_agent_tool_uses",
        session_tool_counts["agent_with_team_name"] >= required_agents,
        f"session JSONL team-scoped Agent tool_use count below {required_agents}: {session_tool_counts['agent_with_team_name']}",
    )
    _expect(
        checks,
        blockers,
        "session_direct_message_tool_uses",
        session_tool_counts["send_message"] >= required_messages,
        f"session JSONL SendMessage tool_use count below {required_messages}: {session_tool_counts['send_message']}",
    )

    return _result(checks, blockers)


def _validate_claude_k(proof: dict[str, Any], base: Path, checks: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> None:
    if proof.get("answer_path"):
        _validate_file_output(proof, base, checks, blockers, "answer_path")
    _validate_file_output(proof, base, checks, blockers, "transcript_path")
    status_path = _resolve(base, proof.get("status_path", ""))
    if not status_path:
        _expect(checks, blockers, "status_path_present", False, "status_path missing")
        return
    if not status_path.exists():
        _expect(checks, blockers, "status_path_exists", False, f"status path missing: {status_path}")
        return
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _expect(checks, blockers, "status_json_parseable", False, f"malformed status JSON: {exc}")
        return
    _expect(checks, blockers, "status_json_parseable", True, "")
    _expect(checks, blockers, "status_not_timed_out", status.get("timed_out") is not True, "status says timed out")
    _expect(checks, blockers, "status_not_failed", status.get("verdict") not in {"failed", "timeout"}, f"bad status verdict: {status.get('verdict')}")


def _validate_gemini_cli(proof: dict[str, Any], base: Path, checks: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> None:
    _validate_file_output(proof, base, checks, blockers, "answer_path")
    status_path = _resolve(base, proof.get("status_path", ""))
    if not status_path:
        _expect(checks, blockers, "status_path_present", False, "status_path missing")
        return
    if not status_path.exists():
        _expect(checks, blockers, "status_path_exists", False, f"status path missing: {status_path}")
        return
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _expect(checks, blockers, "status_json_parseable", False, f"malformed status JSON: {exc}")
        return
    _expect(checks, blockers, "status_json_parseable", True, "")
    _expect(checks, blockers, "status_not_timed_out", status.get("timed_out") is not True, "status says timed out")
    _expect(checks, blockers, "status_completed", status.get("status") == "completed", f"bad status: {status.get('status')}")


def _validate_file_output(
    proof: dict[str, Any],
    base: Path,
    checks: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    path_key: str,
) -> None:
    output_path = _resolve(base, proof.get(path_key, ""))
    if not output_path:
        _expect(checks, blockers, f"{path_key}_present", False, f"{path_key} missing")
        return
    if not output_path.exists():
        _expect(checks, blockers, f"{path_key}_exists", False, f"{path_key} missing: {output_path}")
        return
    _expect(checks, blockers, f"{path_key}_exists", True, "")
    marker = proof.get("completion_marker")
    if not marker:
        _expect(checks, blockers, "completion_marker_present", False, "completion marker missing")
        return
    text = output_path.read_text(encoding="utf-8", errors="replace")
    _expect(checks, blockers, "completion_marker_found", marker in text, f"completion marker not found: {marker}")


def _expect_artifact(checks: list[dict[str, Any]], blockers: list[dict[str, Any]], base: Path, rel: str | None, name: str) -> Path | None:
    path = _resolve(base, rel or "")
    if not path:
        _expect(checks, blockers, name, False, "artifact path missing")
        return None
    exists = path.exists()
    _expect(checks, blockers, name, exists, f"artifact missing: {path}")
    return path if exists else None


def _read_text(path: Path | None) -> str:
    if not path:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _marker_list(proof: dict[str, Any], key: str, default: list[str]) -> list[str]:
    markers = proof.get(key)
    if isinstance(markers, list) and all(isinstance(item, str) and item for item in markers):
        return markers
    return default


def _contains_any(text: str, markers: list[str]) -> bool:
    return any(marker in text for marker in markers)


def _count_marker_lines(text: str, markers: list[str]) -> int:
    count = 0
    for line in text.splitlines():
        if any(marker in line for marker in markers):
            count += 1
    return count


def _count_team_scoped_agent_markers(text: str, team_name: str) -> int:
    if not team_name:
        return 0
    team_pattern = re.compile(rf"team[_-]?name\s*[:=]\s*['\"]?{re.escape(team_name)}['\"]?")
    count = 0
    for line in text.splitlines():
        if "Agent" in line and team_pattern.search(line):
            count += 1
    return count


def _session_tool_counts(paths: list[Path], team_name: str) -> dict[str, int]:
    counts = {
        "team_create": 0,
        "team_state_equivalent": 0,
        "task_create": 0,
        "agent_with_team_name": 0,
        "send_message": 0,
    }
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for tool in _iter_tool_uses(payload):
                    name = str(tool.get("name", ""))
                    tool_input = tool.get("input", {})
                    if name == "TeamCreate":
                        counts["team_create"] += 1
                    elif name == "TaskCreate":
                        counts["task_create"] += 1
                    elif name == "Agent" and _json_contains(tool_input, team_name):
                        counts["agent_with_team_name"] += 1
                    elif name == "SendMessage":
                        counts["send_message"] += 1
                result = payload.get("toolUseResult")
                if isinstance(result, dict) and _team_state_result_matches(result, team_name):
                    counts["team_state_equivalent"] += 1
    return counts


def _iter_tool_uses(payload: dict[str, Any]):
    message = payload.get("message")
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_use":
            yield item


def _json_contains(value: Any, needle: str) -> bool:
    if not needle:
        return False
    return needle in json.dumps(value, ensure_ascii=False, sort_keys=True)


def _team_state_result_matches(result: dict[str, Any], team_name: str) -> bool:
    if not team_name:
        return False
    result_team = str(result.get("team_name") or "")
    team_file_path = str(result.get("team_file_path") or "")
    lead_agent_id = str(result.get("lead_agent_id") or "")
    return result_team == team_name or team_name in team_file_path or team_name in lead_agent_id


def _resolve(base: Path, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def _expect(checks: list[dict[str, Any]], blockers: list[dict[str, Any]], name: str, passed: bool, reason: str) -> None:
    checks.append({"check_id": f"PF-{len(checks) + 1:03d}", "name": name, "status": "pass" if passed else "fail"})
    if not passed:
        blockers.append({"check": name, "reason": reason})


def _result(checks: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "pass" if not blockers else "fail", "checks": checks, "blockers": blockers}
