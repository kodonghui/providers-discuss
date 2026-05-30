from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .artifacts import utc_now, write_json


AUTH_PREFLIGHT_SCHEMA = "providers-discuss.provider-auth-preflight.v1"

STATUS_INSTALLED_LOGGED_IN = "installed_logged_in"
STATUS_INSTALLED_NOT_LOGGED_IN = "installed_not_logged_in"
STATUS_MISSING_CLI = "missing_cli"
STATUS_MANUAL_OR_SKIPPED = "manual_or_skipped"

AUTH_STATUSES = {
    STATUS_INSTALLED_LOGGED_IN,
    STATUS_INSTALLED_NOT_LOGGED_IN,
    STATUS_MISSING_CLI,
    STATUS_MANUAL_OR_SKIPPED,
}

DEFAULT_CLI_BY_TRANSPORT = {
    "codex_exec_file": "codex",
    "claude_k": "claude",
    "claude_k_team_agents": "claude",
    "gemini_cli": "gemini",
}

LOGIN_HINT_BY_TRANSPORT = {
    "codex_exec_file": "Run `codex login` or `codex login --with-api-key` using your own credentials; if the CLI emits a login URL, open that URL yourself.",
    "claude_k": "Run `claude auth login` and complete the official Claude Code login flow; if the CLI emits a login URL, open that URL yourself.",
    "claude_k_team_agents": "Run `claude auth login` and complete the official Claude Code login flow; if the CLI emits a login URL, open that URL yourself.",
    "gemini_cli": "Run `gemini` and complete `/auth`, or configure `GEMINI_API_KEY`/Vertex env auth; if the CLI emits a login URL, open that URL yourself.",
    "manual": "Manual/import seats do not need provider OAuth.",
}


def parse_cli_path_overrides(items: list[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --cli-path, expected key=/path: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid --cli-path key: {item}")
        overrides[key] = Path(value)
    return overrides


def run_auth_preflight(
    *,
    config: dict[str, Any],
    config_path: Path | None = None,
    report_dir: Path | None = None,
    cli_overrides: dict[str, Path] | None = None,
    timeout_seconds: int = 3,
) -> dict[str, Any]:
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    cli_overrides = cli_overrides or {}
    seats = [seat for seat in config.get("seats", []) if isinstance(seat, dict) and seat.get("enabled", True) is not False]
    reports = [
        inspect_seat_auth(seat=seat, cli_overrides=cli_overrides, timeout_seconds=timeout_seconds)
        for seat in seats
    ]
    blockers = [
        {
            "seat_id": item["seat_id"],
            "provider": item["provider"],
            "transport": item["transport"],
            "status": item["status"],
            "login_hint": item["login_hint"],
        }
        for item in reports
        if item["blocker"]
    ]
    optional_issues = [
        {
            "seat_id": item["seat_id"],
            "status": item["status"],
            "next_action": item["next_action"],
        }
        for item in reports
        if item["optional_issue"]
    ]
    status = "fail" if blockers else ("partial" if optional_issues else "pass")
    payload = {
        "schema": AUTH_PREFLIGHT_SCHEMA,
        "generated_at": utc_now(),
        "config_path": str(config_path) if config_path else "",
        "status": status,
        "seats": reports,
        "blockers": blockers,
        "optional_issues": optional_issues,
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }
    if report_dir:
        write_auth_reports(report_dir, payload)
    return payload


def inspect_seat_auth(
    *,
    seat: dict[str, Any],
    cli_overrides: dict[str, Path] | None = None,
    timeout_seconds: int = 3,
) -> dict[str, Any]:
    cli_overrides = cli_overrides or {}
    seat_id = str(seat.get("seat_id") or "")
    provider = str(seat.get("provider") or "")
    transport = str(seat.get("transport") or "")
    required = seat.get("required", True) is not False
    if transport == "manual" or provider == "manual":
        status = STATUS_MANUAL_OR_SKIPPED
        cli_path = ""
        probe = "none"
    else:
        cli_path = _resolve_cli_path(seat=seat, cli_overrides=cli_overrides)
        if not cli_path or not _cli_path_is_executable(cli_path):
            status = STATUS_MISSING_CLI
            probe = "which"
        else:
            status, probe = _probe_login_status(seat=seat, transport=transport, cli_path=cli_path, timeout_seconds=timeout_seconds)
    blocker = required and status in {STATUS_MISSING_CLI, STATUS_INSTALLED_NOT_LOGGED_IN}
    optional_issue = (not required) and status in {STATUS_MISSING_CLI, STATUS_INSTALLED_NOT_LOGGED_IN}
    login_hint = login_hint_for_transport(transport)
    return {
        "seat_id": seat_id,
        "provider": provider,
        "transport": transport,
        "required": required,
        "status": status,
        "cli_path": _safe_cli_path(cli_path),
        "probe": probe,
        "login_hint": login_hint,
        "blocker": blocker,
        "optional_issue": optional_issue,
        "next_action": _next_action(required=required, status=status, login_hint=login_hint),
    }


def write_auth_reports(report_dir: Path, payload: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(report_dir / "provider-auth-preflight.json", payload)
    (report_dir / "provider-auth-preflight.md").write_text(auth_report_markdown(payload), encoding="utf-8")


def auth_report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Provider Auth Preflight",
        "",
        f"- schema: `{payload['schema']}`",
        f"- status: `{payload['status']}`",
        f"- config_path: `{payload.get('config_path', '')}`",
        "- secret_policy: OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
        "",
        "## Seats",
        "",
        "| seat_id | provider | transport | required | status | blocker | next_action |",
        "|---|---|---|---:|---|---:|---|",
    ]
    for seat in payload.get("seats", []):
        lines.append(
            "| `{seat_id}` | `{provider}` | `{transport}` | {required} | `{status}` | {blocker} | {next_action} |".format(
                seat_id=seat.get("seat_id", ""),
                provider=seat.get("provider", ""),
                transport=seat.get("transport", ""),
                required=seat.get("required") is True,
                status=seat.get("status", ""),
                blocker=seat.get("blocker") is True,
                next_action=str(seat.get("next_action") or "").replace("|", "/"),
            )
        )
    if payload.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        for blocker in payload["blockers"]:
            lines.append(f"- `{blocker['seat_id']}` status `{blocker['status']}`: {blocker['login_hint']}")
    return "\n".join(lines) + "\n"


def login_hint_for_transport(transport: str) -> str:
    return LOGIN_HINT_BY_TRANSPORT.get(transport, "Install and authenticate the configured provider CLI, then rerun auth-preflight.")


def _resolve_cli_path(*, seat: dict[str, Any], cli_overrides: dict[str, Path]) -> str:
    keys = [
        str(seat.get("seat_id") or ""),
        str(seat.get("transport") or ""),
        str(seat.get("provider") or ""),
        DEFAULT_CLI_BY_TRANSPORT.get(str(seat.get("transport") or ""), ""),
    ]
    for key in keys:
        if key and key in cli_overrides:
            return str(cli_overrides[key])
    command = DEFAULT_CLI_BY_TRANSPORT.get(str(seat.get("transport") or ""))
    if not command:
        return ""
    return shutil.which(command) or ""


def _probe_login_status(*, seat: dict[str, Any], transport: str, cli_path: str, timeout_seconds: int) -> tuple[str, str]:
    commands = _probe_commands(seat=seat, transport=transport, cli_path=cli_path)
    if not commands:
        return STATUS_INSTALLED_NOT_LOGGED_IN, "installed_only"
    for probe_name, command in commands:
        result = _run_probe(command, timeout_seconds=timeout_seconds)
        if result is None:
            continue
        status = _status_from_probe(probe_name=probe_name, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if status == STATUS_INSTALLED_LOGGED_IN:
            return status, probe_name
    return STATUS_INSTALLED_NOT_LOGGED_IN, commands[-1][0]


def _probe_commands(*, seat: dict[str, Any], transport: str, cli_path: str) -> list[tuple[str, list[str]]]:
    if transport == "codex_exec_file":
        return [("codex_login_status", [cli_path, "login", "status"])]
    if transport in {"claude_k", "claude_k_team_agents"}:
        return [("claude_auth_status", [cli_path, "auth", "status", "--json"])]
    if transport == "gemini_cli":
        model = _seat_model(seat)
        command = [cli_path, "-p", "Reply with exactly: GEMINI_AUTH_OK", "--output-format", "json"]
        if model:
            command.extend(["--model", model])
        return [("gemini_headless_probe", command)]
    return []


def _run_probe(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str] | None:
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "1")
    try:
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _status_from_probe(*, probe_name: str, returncode: int, stdout: str, stderr: str) -> str:
    if returncode != 0:
        return STATUS_INSTALLED_NOT_LOGGED_IN
    text = "\n".join([stdout or "", stderr or ""]).strip()
    if probe_name == "claude_auth_status":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return STATUS_INSTALLED_LOGGED_IN if _looks_logged_in(text) else STATUS_INSTALLED_NOT_LOGGED_IN
        return STATUS_INSTALLED_LOGGED_IN if payload.get("loggedIn") is True else STATUS_INSTALLED_NOT_LOGGED_IN
    if probe_name == "codex_login_status":
        return STATUS_INSTALLED_LOGGED_IN if _looks_logged_in(text) else STATUS_INSTALLED_NOT_LOGGED_IN
    if probe_name == "gemini_headless_probe":
        return STATUS_INSTALLED_LOGGED_IN if _gemini_probe_ok(text) else STATUS_INSTALLED_NOT_LOGGED_IN
    return STATUS_INSTALLED_LOGGED_IN if _looks_logged_in(text) else STATUS_INSTALLED_NOT_LOGGED_IN


def _looks_logged_in(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\bnot\s+logged\s+in\b|\blogged\s+out\b|\bunauth", lowered):
        return False
    return "logged in" in lowered or "logged_in" in lowered or '"loggedin": true' in lowered.replace(" ", "")


def _gemini_probe_ok(text: str) -> bool:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "GEMINI_AUTH_OK" in text
    if isinstance(payload, dict):
        response = payload.get("response")
        if isinstance(response, str) and response.strip() == "GEMINI_AUTH_OK":
            return True
        error = payload.get("error")
        if error:
            return False
    return False


def _seat_model(seat: dict[str, Any]) -> str:
    execution = seat.get("execution") if isinstance(seat.get("execution"), dict) else {}
    return str(seat.get("model") or execution.get("model") or "").strip()


def _safe_cli_path(path: str) -> str:
    if not path:
        return ""
    return str(Path(path))


def _cli_path_is_executable(path: str) -> bool:
    candidate = Path(path)
    return candidate.exists() and os.access(candidate, os.X_OK)


def _next_action(*, required: bool, status: str, login_hint: str) -> str:
    if status in {STATUS_INSTALLED_LOGGED_IN, STATUS_MANUAL_OR_SKIPPED}:
        return "continue"
    if required:
        return login_hint
    return "disable this optional seat or authenticate it before live dispatch"
