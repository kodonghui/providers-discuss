from __future__ import annotations

import json
import re
import shlex
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOOK_EVENTS = ("UserPromptSubmit", "TaskCreated", "TeammateIdle", "TaskCompleted")
HOOK_MARKER = "kdh-providers-discuss hook"


def inspect_workspace_trust(*, claude_json: Path, workspace: Path) -> dict[str, Any]:
    workspace_key = str(workspace.resolve())
    data = _read_claude_json(claude_json)
    project = _project_entry(data, workspace_key)
    trusted = project.get("hasTrustDialogAccepted") is True
    return {
        "schema": "kdh.providers-discuss.claude-workspace-trust.v1",
        "claude_json": str(claude_json),
        "workspace": workspace_key,
        "project_exists": workspace_key in (data.get("projects") or {}),
        "hasTrustDialogAccepted": project.get("hasTrustDialogAccepted"),
        "status": "trusted" if trusted else "not_trusted",
        "changed": False,
        "backup_path": "",
    }


def repair_workspace_trust(*, claude_json: Path, workspace: Path) -> dict[str, Any]:
    workspace_key = str(workspace.resolve())
    data = _read_claude_json(claude_json)
    projects = data.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise ValueError("Claude workspace trust projects field is not an object")
    project = projects.setdefault(workspace_key, {})
    if not isinstance(project, dict):
        raise ValueError(f"project entry is not an object: {workspace_key}")
    before = project.get("hasTrustDialogAccepted")
    result = inspect_workspace_trust(claude_json=claude_json, workspace=workspace)
    if before is True:
        return result
    backup = _backup_path(claude_json)
    claude_json.parent.mkdir(parents=True, exist_ok=True)
    if claude_json.exists():
        shutil.copy2(claude_json, backup)
    else:
        backup.write_text("{}\n", encoding="utf-8")
    project["hasTrustDialogAccepted"] = True
    _write_json(claude_json, data)
    result = inspect_workspace_trust(claude_json=claude_json, workspace=workspace)
    result["changed"] = True
    result["before_hasTrustDialogAccepted"] = before
    result["backup_path"] = str(backup)
    return result


def inspect_permissions(*, settings_json: Path) -> dict[str, Any]:
    data = _read_settings_json(settings_json)
    permissions = data.get("permissions") or {}
    if not isinstance(permissions, dict):
        permissions = {}
    default_mode = permissions.get("defaultMode")
    skip_auto_prompt = data.get("skipAutoPermissionPrompt")
    auto = default_mode == "auto" and skip_auto_prompt is True
    return {
        "schema": "kdh.providers-discuss.claude-permissions.v1",
        "settings_json": str(settings_json),
        "permissions_defaultMode": default_mode,
        "skipAutoPermissionPrompt": skip_auto_prompt,
        "status": "auto" if auto else "not_auto",
        "changed": False,
        "backup_path": "",
    }


def repair_permissions(*, settings_json: Path) -> dict[str, Any]:
    data = _read_settings_json(settings_json)
    permissions = data.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("Claude settings permissions field is not an object")
    before = {
        "permissions_defaultMode": permissions.get("defaultMode"),
        "skipAutoPermissionPrompt": data.get("skipAutoPermissionPrompt"),
    }
    if before["permissions_defaultMode"] == "auto" and before["skipAutoPermissionPrompt"] is True:
        return inspect_permissions(settings_json=settings_json)
    backup = _backup_existing_json(settings_json)
    permissions["defaultMode"] = "auto"
    data["skipAutoPermissionPrompt"] = True
    _write_json(settings_json, data)
    result = inspect_permissions(settings_json=settings_json)
    result["changed"] = True
    result["before"] = before
    result["backup_path"] = str(backup)
    return result


def inspect_hook_config(
    *,
    settings_json: Path,
    harness_root: Path,
    root: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: str,
) -> dict[str, Any]:
    trigger_regex = _normalize_trigger_regex(run_id, trigger_regex)
    data = _read_settings_json(settings_json)
    expected = _expected_hook_commands(
        harness_root=harness_root,
        root=root,
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        trigger_mode=trigger_mode,
        trigger_regex=trigger_regex,
        roles=roles,
    )
    configured = []
    for event, command in expected.items():
        if _event_has_hook_command(data, event, command, run_id):
            configured.append(event)
    stale = [event for event, command in expected.items() if _event_has_stale_hook_command(data, event, command, run_id)]
    missing = [event for event in HOOK_EVENTS if event not in configured]
    if not configured:
        status = "not_configured"
    elif missing:
        status = "partially_configured"
    elif stale:
        status = "stale_configured"
    else:
        status = "configured"
    return {
        "schema": "kdh.providers-discuss.claude-hook-config.v1",
        "settings_json": str(settings_json),
        "harness_root": str(harness_root.resolve()),
        "root": str(root.resolve()),
        "run_id": run_id,
        "round_id": round_id,
        "seat_id": seat_id,
        "trigger_mode": trigger_mode,
        "scope": "global_dispatcher",
        "configured_events": configured,
        "missing_events": missing,
        "stale_events": stale,
        "status": status,
        "changed": False,
        "backup_path": "",
        "hook_marker": HOOK_MARKER,
    }


def repair_hook_config(
    *,
    settings_json: Path,
    harness_root: Path,
    root: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: str,
) -> dict[str, Any]:
    trigger_regex = _normalize_trigger_regex(run_id, trigger_regex)
    data = _read_settings_json(settings_json)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude settings hooks field is not an object")
    expected = _expected_hook_commands(
        harness_root=harness_root,
        root=root,
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        trigger_mode=trigger_mode,
        trigger_regex=trigger_regex,
        roles=roles,
    )
    stale = [event for event, command in expected.items() if _event_has_stale_hook_command(data, event, command, run_id)]
    missing = [event for event, command in expected.items() if not _event_has_hook_command(data, event, command, run_id)]
    if not missing and not stale:
        return inspect_hook_config(
            settings_json=settings_json,
            harness_root=harness_root,
            root=root,
            run_id=run_id,
            round_id=round_id,
            seat_id=seat_id,
            trigger_mode=trigger_mode,
            trigger_regex=trigger_regex,
            roles=roles,
        )
    backup = _backup_existing_json(settings_json)
    for event, command in expected.items():
        _remove_stale_hook_commands(data, event, command, run_id)
    missing = [event for event, command in expected.items() if not _event_has_hook_command(data, event, command, run_id)]
    for event in missing:
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude settings hooks.{event} field is not a list")
        entries.append(
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": expected[event],
                        "timeout": 30,
                    }
                ],
            }
        )
    _write_json(settings_json, data)
    result = inspect_hook_config(
        settings_json=settings_json,
        harness_root=harness_root,
        root=root,
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        trigger_mode=trigger_mode,
        trigger_regex=trigger_regex,
        roles=roles,
    )
    result["changed"] = True
    result["installed_events"] = missing
    result["replaced_stale_events"] = stale
    result["backup_path"] = str(backup)
    return result


def remove_hook_config(
    *,
    settings_json: Path,
    harness_root: Path,
    root: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: str,
) -> dict[str, Any]:
    trigger_regex = _normalize_trigger_regex(run_id, trigger_regex)
    data = _read_settings_json(settings_json)
    expected = _expected_hook_commands(
        harness_root=harness_root,
        root=root,
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        trigger_mode=trigger_mode,
        trigger_regex=trigger_regex,
        roles=roles,
    )
    updated = deepcopy(data)
    removed_by_event = {
        event: _remove_dispatcher_hook_commands(updated, event, command)
        for event, command in expected.items()
    }
    removed_events = [event for event, count in removed_by_event.items() if count > 0]
    if not removed_events:
        result = inspect_hook_config(
            settings_json=settings_json,
            harness_root=harness_root,
            root=root,
            run_id=run_id,
            round_id=round_id,
            seat_id=seat_id,
            trigger_mode=trigger_mode,
            trigger_regex=trigger_regex,
            roles=roles,
        )
        result["remove_status"] = "not_configured"
        result["removed_events"] = []
        result["removed_command_count"] = 0
        return result
    backup = _backup_existing_json(settings_json)
    _write_json(settings_json, updated)
    post = inspect_hook_config(
        settings_json=settings_json,
        harness_root=harness_root,
        root=root,
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        trigger_mode=trigger_mode,
        trigger_regex=trigger_regex,
        roles=roles,
    )
    post["status"] = "removed"
    post["post_status"] = inspect_hook_config(
        settings_json=settings_json,
        harness_root=harness_root,
        root=root,
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        trigger_mode=trigger_mode,
        trigger_regex=trigger_regex,
        roles=roles,
    )["status"]
    post["changed"] = True
    post["removed_events"] = removed_events
    post["removed_command_count"] = sum(removed_by_event.values())
    post["backup_path"] = str(backup)
    return post


def inspect_runtime_preflight(
    *,
    claude_json: Path,
    settings_json: Path,
    workspace: Path,
    harness_root: Path,
    root: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: str,
    repair: bool,
    install_hook: bool,
) -> dict[str, Any]:
    trigger_regex = _normalize_trigger_regex(run_id, trigger_regex)
    workspace_result = (
        repair_workspace_trust(claude_json=claude_json, workspace=workspace)
        if repair
        else inspect_workspace_trust(claude_json=claude_json, workspace=workspace)
    )
    permissions_result = repair_permissions(settings_json=settings_json) if repair else inspect_permissions(settings_json=settings_json)
    require_hook = trigger_mode in {"providers_discuss_hook", "global_hook"}
    if require_hook:
        hook_result = (
            repair_hook_config(
                settings_json=settings_json,
                harness_root=harness_root,
                root=root,
                run_id=run_id,
                round_id=round_id,
                seat_id=seat_id,
                trigger_mode=trigger_mode,
                trigger_regex=trigger_regex,
                roles=roles,
            )
            if install_hook
            else inspect_hook_config(
                settings_json=settings_json,
                harness_root=harness_root,
                root=root,
                run_id=run_id,
                round_id=round_id,
                seat_id=seat_id,
                trigger_mode=trigger_mode,
                trigger_regex=trigger_regex,
                roles=roles,
            )
        )
    else:
        hook_result = {
            "schema": "kdh.providers-discuss.claude-hook-config.v1",
            "settings_json": str(settings_json),
            "run_id": run_id,
            "trigger_mode": trigger_mode,
            "status": "not_required",
            "configured_events": [],
            "missing_events": [],
            "changed": False,
            "backup_path": "",
            "hook_marker": HOOK_MARKER,
        }
    blockers = []
    if workspace_result["status"] != "trusted":
        blockers.append(
            {
                "check": "workspace_trust",
                "reason": "workspace is not trusted",
                "next_action": "rerun runtime-preflight with --repair or run trust-workspace --repair for the selected workspace",
            }
        )
    if permissions_result["status"] != "auto":
        blockers.append(
            {
                "check": "permissions",
                "reason": "Claude permission mode is not auto",
                "next_action": "rerun runtime-preflight with --repair or run permissions --repair for the selected settings file",
            }
        )
    if require_hook and hook_result["status"] != "configured":
        blockers.append(
            {
                "check": "hook_config",
                "reason": "requested trigger mode requires installed hook config",
                "next_action": "rerun runtime-preflight with --install-hook or run hook-config --repair for this root",
            }
        )
    next_actions = _runtime_next_actions(
        blockers=blockers,
        trigger_mode=trigger_mode,
        require_hook=require_hook,
        hook_status=str(hook_result.get("status") or ""),
    )
    return {
        "schema": "kdh.providers-discuss.claude-runtime-preflight.v1",
        "status": "pass" if not blockers else "fail",
        "trigger_mode": trigger_mode,
        "hook_required": require_hook,
        "repair": repair,
        "install_hook": install_hook,
        "workspace_trust": workspace_result,
        "permissions": permissions_result,
        "hook_config": hook_result,
        "blockers": blockers,
        "next_action": next_actions[0] if next_actions else "",
        "next_actions": next_actions,
    }


def _read_claude_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"projects": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed Claude config JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Claude config root is not an object: {path}")
    return data


def _read_settings_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed Claude settings JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Claude settings root is not an object: {path}")
    return data


def _project_entry(data: dict[str, Any], workspace_key: str) -> dict[str, Any]:
    projects = data.get("projects") or {}
    if not isinstance(projects, dict):
        return {}
    project = projects.get(workspace_key) or {}
    return project if isinstance(project, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _backup_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}.{stamp}.bak")


def _backup_existing_json(path: Path) -> Path:
    backup = _backup_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, backup)
    else:
        backup.write_text("{}\n", encoding="utf-8")
    return backup


def _expected_hook_commands(
    *,
    harness_root: Path,
    root: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: str,
) -> dict[str, str]:
    trigger_regex = _normalize_trigger_regex(run_id, trigger_regex)
    commands = {}
    command_path = _hook_dispatch_command_path(harness_root)
    for event in HOOK_EVENTS:
        inner = " ".join(
            [
                "cd",
                shlex.quote(str(harness_root.resolve())),
                "&&",
                shlex.quote(command_path),
                "hook-dispatch",
                "--event",
                shlex.quote(event),
                "--root",
                shlex.quote(str(root.resolve())),
                "--seat",
                shlex.quote(seat_id),
                "--trigger-mode",
                shlex.quote(trigger_mode),
                "--roles",
                shlex.quote(roles),
            ]
        )
        commands[event] = "bash -lc " + shlex.quote(inner)
    return commands


def _hook_dispatch_command_path(harness_root: Path) -> str:
    harness_script = harness_root / "scripts" / "kdh-providers-discuss"
    if harness_script.exists():
        return "scripts/kdh-providers-discuss"
    package_script = harness_root / "bin" / "providers-discuss"
    if package_script.exists():
        return "bin/providers-discuss"
    return "providers-discuss"


def _event_has_hook_command(data: dict[str, Any], event: str, expected_command: str, run_id: str) -> bool:
    hooks = data.get("hooks") or {}
    if not isinstance(hooks, dict):
        return False
    entries = hooks.get(event) or []
    if not isinstance(entries, list):
        return False
    for entry in entries:
        for command in _commands_from_hook_entry(entry):
            if command == expected_command:
                return True
    return False


def _event_has_stale_hook_command(data: dict[str, Any], event: str, expected_command: str, run_id: str) -> bool:
    hooks = data.get("hooks") or {}
    if not isinstance(hooks, dict):
        return False
    entries = hooks.get(event) or []
    if not isinstance(entries, list):
        return False
    return any(_is_stale_hook_command(command, expected_command, run_id) for entry in entries for command in _commands_from_hook_entry(entry))


def _remove_stale_hook_commands(data: dict[str, Any], event: str, expected_command: str, run_id: str) -> None:
    hooks = data.get("hooks") or {}
    if not isinstance(hooks, dict):
        return
    entries = hooks.get(event) or []
    if not isinstance(entries, list):
        return
    retained_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            retained_entries.append(entry)
            continue
        command = entry.get("command")
        if isinstance(command, str) and _is_stale_hook_command(command, expected_command, run_id):
            entry = {key: value for key, value in entry.items() if key != "command"}
        nested = entry.get("hooks")
        if isinstance(nested, list):
            nested = [
                item
                for item in nested
                if not (
                    isinstance(item, dict)
                    and isinstance(item.get("command"), str)
                    and _is_stale_hook_command(item["command"], expected_command, run_id)
                )
            ]
            entry["hooks"] = nested
        if entry.get("command") or entry.get("hooks") or any(key not in {"command", "hooks"} for key in entry):
            if entry.get("hooks") == [] and not entry.get("command"):
                continue
            retained_entries.append(entry)
    hooks[event] = retained_entries


def _remove_dispatcher_hook_commands(data: dict[str, Any], event: str, expected_command: str) -> int:
    hooks = data.get("hooks") or {}
    if not isinstance(hooks, dict):
        return 0
    entries = hooks.get(event) or []
    if not isinstance(entries, list):
        return 0
    expected_root = _hook_option_value(expected_command, "--root")
    retained_entries = []
    removed = 0
    for entry in entries:
        if not isinstance(entry, dict):
            retained_entries.append(entry)
            continue
        entry = dict(entry)
        command = entry.get("command")
        if isinstance(command, str) and _is_matching_dispatcher_command(command, expected_root):
            entry.pop("command", None)
            removed += 1
        nested = entry.get("hooks")
        if isinstance(nested, list):
            kept_nested = []
            for item in nested:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("command"), str)
                    and _is_matching_dispatcher_command(item["command"], expected_root)
                ):
                    removed += 1
                    continue
                kept_nested.append(item)
            entry["hooks"] = kept_nested
        if entry.get("command") or entry.get("hooks") or any(key not in {"command", "hooks"} for key in entry):
            if entry.get("hooks") == [] and not entry.get("command"):
                continue
            retained_entries.append(entry)
    hooks[event] = retained_entries
    return removed


def _is_matching_dispatcher_command(command: str, expected_root: str) -> bool:
    if HOOK_MARKER not in command or " hook-dispatch " not in command:
        return False
    return bool(expected_root) and _hook_option_value(command, "--root") == expected_root


def _is_stale_hook_command(command: str, expected_command: str, run_id: str) -> bool:
    if command == expected_command or HOOK_MARKER not in command:
        return False
    if " hook-dispatch " not in command:
        return True
    return _hook_option_value(command, "--root") == _hook_option_value(expected_command, "--root")


def _hook_option_value(command: str, option: str) -> str:
    for candidate in _hook_command_tokens(command):
        if option in candidate:
            index = candidate.index(option)
            if index + 1 < len(candidate):
                return candidate[index + 1]
    match = re.search(rf"{re.escape(option)}\s+(?:'([^']*)'|\"([^\"]*)\"|(\S+))", command)
    if not match:
        return ""
    return next((group for group in match.groups() if group is not None), "")


def _hook_command_tokens(command: str) -> list[list[str]]:
    candidates: list[list[str]] = []
    try:
        outer = shlex.split(command)
    except ValueError:
        outer = []
    if outer:
        candidates.append(outer)
    if len(outer) >= 3 and outer[0] == "bash" and outer[1] == "-lc":
        try:
            candidates.append(shlex.split(outer[2]))
        except ValueError:
            pass
    return candidates


def _commands_from_hook_entry(entry: Any) -> list[str]:
    commands: list[str] = []
    if not isinstance(entry, dict):
        return commands
    command = entry.get("command")
    if isinstance(command, str):
        commands.append(command)
    nested = entry.get("hooks")
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict) and isinstance(item.get("command"), str):
                commands.append(item["command"])
    return commands


def _normalize_trigger_regex(run_id: str, trigger_regex: str) -> str:
    return trigger_regex or re.escape(run_id)


def _runtime_next_actions(
    *,
    blockers: list[dict[str, str]],
    trigger_mode: str,
    require_hook: bool,
    hook_status: str,
) -> list[str]:
    if blockers:
        return [str(blocker.get("next_action") or blocker.get("reason") or blocker.get("check") or "") for blocker in blockers]
    if not require_hook:
        return [
            "generate a prompt-only Team Agents contract with team-agents-prompt, or run smoke-claude-team-agents --trigger-mode prompt_only",
        ]
    if hook_status == "configured":
        return [f"run smoke-claude-team-agents with --trigger-mode {trigger_mode} after preparing the run prompt"]
    return ["inspect hook-config; install only with explicit --repair or runtime-preflight --install-hook"]
