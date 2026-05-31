from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent_profiles import render_agent_profile_contract
from .artifacts import DEFAULT_PROVIDER_TIMEOUT_SECONDS, copy_answer, sha256_file, write_artifact_hash, write_json


ADAPTER_RESULT_SCHEMA = "kdh.providers-discuss.adapter-result.v1"
ADAPTER_STATUS_SCHEMA = "kdh.providers-discuss.adapter-status.v1"
ADAPTER_PROOF_SCHEMA = "kdh.providers-discuss.adapter-proof.v1"
ADAPTER_PREVIEW_SCHEMA = "kdh.providers-discuss.command-preview.v1"

FAILURE_MISSING_CLI = "missing_cli"
FAILURE_INSTALLED_NOT_LOGGED_IN = "installed_not_logged_in"
FAILURE_WORKSPACE_TRUST_PROMPT = "workspace_trust_prompt"
FAILURE_PERMISSION_PROMPT = "permission_prompt"
FAILURE_TIMEOUT = "timeout"
FAILURE_QUOTA_OR_RATE_LIMIT = "quota_or_rate_limit"
FAILURE_PROVIDER_COMMAND_FAILED = "provider_command_failed"
FAILURE_MALFORMED_OUTPUT = "malformed_output"
FAILURE_ANSWER_MISSING = "answer_missing"
FAILURE_PROOF_FAILED = "proof_failed"
FAILURE_UNSUPPORTED_LIVE_DISPATCH = "unsupported_live_dispatch"
FAILURE_MANUAL_IMPORT_SOURCE_MISSING = "manual_import_source_missing"
FAILURE_OPTIONAL_PROVIDER_SKIPPED = "optional_provider_skipped"

NORMALIZED_FAILURE_CLASSES = {
    FAILURE_MISSING_CLI,
    FAILURE_INSTALLED_NOT_LOGGED_IN,
    FAILURE_WORKSPACE_TRUST_PROMPT,
    FAILURE_PERMISSION_PROMPT,
    FAILURE_TIMEOUT,
    FAILURE_QUOTA_OR_RATE_LIMIT,
    FAILURE_PROVIDER_COMMAND_FAILED,
    FAILURE_MALFORMED_OUTPUT,
    FAILURE_ANSWER_MISSING,
    FAILURE_PROOF_FAILED,
    FAILURE_UNSUPPORTED_LIVE_DISPATCH,
    FAILURE_MANUAL_IMPORT_SOURCE_MISSING,
    FAILURE_OPTIONAL_PROVIDER_SKIPPED,
}

SUPPORTED_REASONING_EFFORTS = {
    "default",
    "high",
    "low",
    "manual",
    "max",
    "medium",
    "minimal",
    "xhigh",
}

SECRET_KEY_PARTS = (
    "api_key",
    "cookie",
    "credential",
    "oauth",
    "password",
    "private_key",
    "secret",
    "token",
)
SECRET_VALUE_MARKERS = (
    "--api-key",
    "api_key=",
    "cookie=",
    "credential=",
    "oauth",
    "password=",
    "private_key=",
    "secret=",
    "token=",
)


@dataclass(frozen=True)
class ProviderAdapter:
    adapter_id: str
    transport: str
    provider_ids: tuple[str, ...]
    maturity: str
    live_dispatch: str
    live_dispatch_available: bool
    cli_name: str
    default_timeout_seconds: int = DEFAULT_PROVIDER_TIMEOUT_SECONDS

    def command_preview(self, *, seat: dict[str, Any], prompt_path: str, answer_path: str) -> list[str]:
        execution = _execution(seat)
        model = _safe_label(seat.get("model") or execution.get("model") or "")
        effort = _safe_label(seat.get("reasoning_effort") or execution.get("effort") or "")
        if self.transport == "manual":
            return [f"manual import: provide --answer {seat['seat_id']}=<answer.md>"]
        if self.transport == "codex_exec_file":
            return [
                "runner path: providers-discuss run-round <run-id> --round <round> --mode manual-import "
                f"--answer {seat['seat_id']}=<answer.md>",
                "codex_exec_file live dispatch is structural; do not call codex directly from this prompt",
            ]
        if self.transport == "claude_k":
            return [
                "runner path: providers-discuss smoke-claude-k <run-id> --round <round> "
                f"--seat {seat['seat_id']} --claude-bin <path>",
                "do not use claude -p or direct Claude CLI answer capture for runner-owned proof",
            ]
        if self.transport == "claude_k_team_agents":
            roles = seat.get("team_agents", {}).get("roles") or seat.get("team_agents", {}).get("required_teammates") or []
            labels = [_team_role_label(role) for role in roles]
            return [
                "runner path: providers-discuss smoke-claude-team-agents <run-id> --round <round> "
                f"--seat {seat['seat_id']} --claude-bin <path>",
                "do not use claude -p or direct Claude CLI answer capture for Team Agents proof",
                f"team-agents roles: {', '.join(_safe_label(role) for role in labels) or 'configured'}",
            ]
        if self.transport == "gemini_cli":
            return [
                "cat {prompt} | gemini --prompt 'Execute the provider-discuss prompt from stdin.' "
                "--output-format json --model {model} > {answer}".format(
                    prompt=prompt_path,
                    model=model or "configured",
                    answer=answer_path,
                )
            ]
        return [f"{self.cli_name} < {prompt_path} > {answer_path}"]


ADAPTERS: dict[str, ProviderAdapter] = {
    "manual": ProviderAdapter(
        adapter_id="manual_import",
        transport="manual",
        provider_ids=("manual", "other"),
        maturity="live",
        live_dispatch="manual-import",
        live_dispatch_available=True,
        cli_name="manual",
    ),
    "codex_exec_file": ProviderAdapter(
        adapter_id="codex_exec_file",
        transport="codex_exec_file",
        provider_ids=("openai",),
        maturity="structural",
        live_dispatch="not_implemented_in_p6",
        live_dispatch_available=False,
        cli_name="codex",
    ),
    "claude_k": ProviderAdapter(
        adapter_id="claude_code",
        transport="claude_k",
        provider_ids=("anthropic",),
        maturity="smoke_only",
        live_dispatch="use_smoke_claude_k",
        live_dispatch_available=False,
        cli_name="claude",
    ),
    "claude_k_team_agents": ProviderAdapter(
        adapter_id="claude_team_agents",
        transport="claude_k_team_agents",
        provider_ids=("anthropic",),
        maturity="smoke_only",
        live_dispatch="use_smoke_claude_team_agents",
        live_dispatch_available=False,
        cli_name="claude",
    ),
    "gemini_cli": ProviderAdapter(
        adapter_id="gemini_cli",
        transport="gemini_cli",
        provider_ids=("google",),
        maturity="live_headless",
        live_dispatch="smoke-gemini-headless_or_run-round_live-dispatch",
        live_dispatch_available=True,
        cli_name="gemini",
    ),
}


def adapter_for_seat(seat: dict[str, Any]) -> ProviderAdapter:
    transport = str(seat.get("transport") or "")
    adapter = ADAPTERS.get(transport)
    if not adapter:
        raise ValueError(f"unsupported transport adapter: {transport}")
    return adapter


def validate_adapter_seat(seat: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    transport = str(seat.get("transport") or "")
    provider = str(seat.get("provider") or "")
    adapter = ADAPTERS.get(transport)
    if not adapter:
        blockers.append({"check": "adapter_transport_supported", "reason": f"unsupported transport adapter: {transport}"})
        return blockers
    if provider not in adapter.provider_ids:
        blockers.append(
            {
                "check": "adapter_provider_transport",
                "reason": f"provider {provider} cannot use transport {transport}; expected one of {list(adapter.provider_ids)}",
            }
        )
    effort = str(seat.get("reasoning_effort") or _execution(seat).get("effort") or "default")
    if effort not in SUPPORTED_REASONING_EFFORTS:
        blockers.append({"check": "adapter_reasoning_effort", "reason": f"unsupported reasoning_effort: {effort}"})
    for secret_path in _secret_like_execution_paths(seat.get("execution") or {}):
        blockers.append({"check": "adapter_no_secret_execution_keys", "reason": f"secret-like execution key is not allowed: {secret_path}"})
    return blockers


def adapter_summary(seat: dict[str, Any], *, prompt_path: str = "<prompt>", answer_path: str = "<answer>") -> dict[str, Any]:
    adapter = adapter_for_seat(seat)
    return {
        "seat_id": seat.get("seat_id", ""),
        "adapter_id": adapter.adapter_id,
        "provider": seat.get("provider", ""),
        "transport": adapter.transport,
        "model": seat.get("model") or _execution(seat).get("model") or "",
        "reasoning_effort": seat.get("reasoning_effort") or _execution(seat).get("effort") or "",
        "required": seat.get("required", True) is not False,
        "enabled": seat.get("enabled", True) is not False,
        "timeout_seconds": effective_timeout_seconds(seat),
        "maturity": adapter.maturity,
        "live_dispatch": adapter.live_dispatch,
        "live_dispatch_available": adapter.live_dispatch_available,
        "cli_name": adapter.cli_name,
        "command_preview": adapter.command_preview(seat=seat, prompt_path=prompt_path, answer_path=answer_path),
    }


def effective_timeout_seconds(seat: dict[str, Any]) -> int:
    adapter = adapter_for_seat(seat)
    value = seat.get("timeout_seconds")
    if isinstance(value, int) and value > 0:
        return value
    return adapter.default_timeout_seconds


def write_round_prompt(*, base: Path, run: dict[str, Any], spec: dict[str, Any], seat: dict[str, Any]) -> dict[str, Any]:
    round_id = spec["round_id"]
    seat_id = seat["seat_id"]
    prompt_rel = f"prompts/round-{round_id}/{seat_id}.prompt.md"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}.proof.json"
    preview_rel = f"logs/round-{round_id}/{seat_id}.command-preview.json"
    prompt_path = base / prompt_rel
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(
        render_provider_prompt(
            run=run,
            spec=spec,
            seat=seat,
            prompt_rel=prompt_rel,
            answer_rel=answer_rel,
            status_rel=status_rel,
            proof_rel=proof_rel,
        ),
        encoding="utf-8",
    )
    digest = write_artifact_hash(base, prompt_rel)
    return {
        "schema": ADAPTER_RESULT_SCHEMA,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "status": "prompt_written",
        "answer_path": answer_rel,
        "status_path": status_rel,
        "proof_path": proof_rel,
        "preview_path": preview_rel,
        "log_path": "",
        "exit_code": None,
        "failure_classification": "",
        "required": seat.get("required", True) is not False,
        "refs": [prompt_rel],
        "sha256": digest,
        "adapter": adapter_summary(seat, prompt_path=prompt_rel, answer_path=answer_rel),
    }


def write_dry_run_result(*, base: Path, run: dict[str, Any], spec: dict[str, Any], seat: dict[str, Any]) -> dict[str, Any]:
    prompt_result = write_round_prompt(base=base, run=run, spec=spec, seat=seat)
    round_id = spec["round_id"]
    seat_id = seat["seat_id"]
    required = seat.get("required", True) is not False
    answer_rel = prompt_result["answer_path"]
    status_rel = prompt_result["status_path"]
    proof_rel = prompt_result["proof_path"]
    preview_rel = prompt_result["preview_path"]
    status_path = base / status_rel
    proof_path = base / proof_rel
    preview_path = base / preview_rel
    for path in (status_path, proof_path, preview_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    summary = adapter_summary(seat, prompt_path=prompt_result["refs"][0], answer_path=answer_rel)
    status, failure = _dry_run_status_and_failure(summary=summary, required=required)
    preview_payload = {
        "schema": ADAPTER_PREVIEW_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": summary["adapter_id"],
        "adapter_maturity": summary["maturity"],
        "live_dispatch": summary["live_dispatch"],
        "live_dispatch_available": summary["live_dispatch_available"],
        "timeout_seconds": summary["timeout_seconds"],
        "command_preview": summary["command_preview"],
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }
    status_payload = {
        "schema": ADAPTER_STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": summary["adapter_id"],
        "mode": "dry-run",
        "status": status,
        "required": required,
        "answer_path": "",
        "proof_path": proof_rel,
        "preview_path": preview_rel,
        "exit_code": None,
        "timeout_seconds": summary["timeout_seconds"],
        "failure_classification": failure,
        "command_preview": summary["command_preview"],
        "secret_policy": preview_payload["secret_policy"],
    }
    proof_payload = {
        "schema": ADAPTER_PROOF_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": summary["adapter_id"],
        "proof_kind": "dry_run_preview",
        "status": status,
        "required": required,
        "answer_path": "",
        "status_path": status_rel,
        "preview_path": preview_rel,
        "exit_code": None,
        "failure_classification": failure,
        "adapter_maturity": summary["maturity"],
        "live_dispatch": summary["live_dispatch"],
        "live_dispatch_available": summary["live_dispatch_available"],
        "timeout_seconds": summary["timeout_seconds"],
    }
    write_json(preview_path, preview_payload)
    preview_sha = write_artifact_hash(base, preview_rel)
    write_json(status_path, status_payload)
    status_sha = write_artifact_hash(base, status_rel)
    write_json(proof_path, proof_payload)
    proof_sha = write_artifact_hash(base, proof_rel)
    refs = [*prompt_result["refs"], preview_rel, status_rel, proof_rel]
    return {
        **prompt_result,
        "status": status,
        "answer_path": "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "preview_path": preview_rel,
        "exit_code": None,
        "failure_classification": failure,
        "refs": refs,
        "sha256": {
            "prompt": prompt_result["sha256"],
            "preview": preview_sha,
            "status": status_sha,
            "proof": proof_sha,
        },
        "adapter": summary,
    }


def render_provider_prompt(
    *,
    run: dict[str, Any],
    spec: dict[str, Any],
    seat: dict[str, Any],
    prompt_rel: str,
    answer_rel: str,
    status_rel: str,
    proof_rel: str,
) -> str:
    summary = adapter_summary(seat, prompt_path=prompt_rel, answer_path=answer_rel)
    preview = "\n".join(f"- `{item}`" for item in summary["command_preview"])
    profile_contract = ""
    if isinstance(seat.get("agent_profile"), dict):
        profile_contract = "\n" + render_agent_profile_contract(seat["agent_profile"], assigned_to=f"seat:{seat['seat_id']}")
    return f"""# kdh-providers-discuss Provider Prompt

run_id: `{run['run_id']}`
round_id: `{spec['round_id']}`
round_mode: `{spec['mode']}`
seat_id: `{seat['seat_id']}`
provider: `{seat.get('provider', '')}`
transport: `{seat.get('transport', '')}`
model: `{summary['model']}`
reasoning_effort: `{summary['reasoning_effort']}`
required: `{summary['required']}`
timeout_seconds: `{summary['timeout_seconds']}`
adapter_id: `{summary['adapter_id']}`
adapter_maturity: `{summary['maturity']}`
live_dispatch: `{summary['live_dispatch']}`
live_dispatch_available: `{summary['live_dispatch_available']}`

## Objective

{run['objective']}

## Round Task

{spec['title']}
{profile_contract}

## Command Preview

This preview is sanitized and must not include OAuth tokens, cookies,
provider-home config, credential file bodies, or shell history.

{preview}

## Runner-Owned Artifacts

- answer_path: `{answer_rel}`
- status_path: `{status_rel}`
- proof_path: `{proof_rel}`

Only the Markdown answer content is provider-writable. Do not create, edit, or
overwrite runner-owned status, proof, event, hash, gate, or orchestrator files.
The `providers-discuss` CLI writes those files after it imports or dispatches
the provider answer.

## Required Output

Return a concrete Markdown answer with claims that can later be mapped into
`claims/round-{spec['round_id']}-claim-map.json`.

Do not invent evidence. Do not claim implementation is authorized unless the
gate says so. Do not add output length caps unless the CEO explicitly asked for
one in the current run.
"""


def write_manual_import_result(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    source_path: Path | None,
) -> dict[str, Any]:
    seat_id = seat["seat_id"]
    required = seat.get("required", True) is not False
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}.manual-import.proof.json"
    status_path = base / status_rel
    proof_path = base / proof_rel
    status_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.parent.mkdir(parents=True, exist_ok=True)

    answer_sha = ""
    source_sha = ""
    exit_code: int | None = None
    refs = [status_rel, proof_rel]
    status = "completed"
    failure = ""
    source_label = ""
    if source_path is None:
        status = "failed" if required else "skipped"
        failure = FAILURE_ANSWER_MISSING if required else FAILURE_OPTIONAL_PROVIDER_SKIPPED
    else:
        if not source_path.exists():
            status = "failed" if required else "skipped"
            failure = FAILURE_MANUAL_IMPORT_SOURCE_MISSING
            source_label = str(source_path)
        else:
            copy_answer(source_path, base / answer_rel)
            source_sha = sha256_file(source_path)
            answer_sha = write_artifact_hash(base, answer_rel)
            refs.insert(0, answer_rel)
            exit_code = 0
            source_label = str(source_path)

    summary = adapter_summary(seat, prompt_path=f"prompts/round-{round_id}/{seat_id}.prompt.md", answer_path=answer_rel)
    status_payload = {
        "schema": ADAPTER_STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": summary["adapter_id"],
        "mode": "manual-import",
        "status": status,
        "required": required,
        "answer_path": answer_rel if answer_sha else "",
        "proof_path": proof_rel,
        "exit_code": exit_code,
        "timeout_seconds": summary["timeout_seconds"],
        "failure_classification": failure,
        "command_preview": summary["command_preview"],
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }
    proof_payload = {
        "schema": ADAPTER_PROOF_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": summary["adapter_id"],
        "proof_kind": "manual_import",
        "status": status,
        "required": required,
        "answer_path": answer_rel if answer_sha else "",
        "status_path": status_rel,
        "source_path": source_label,
        "source_sha256": source_sha,
        "answer_sha256": answer_sha,
        "exit_code": exit_code,
        "failure_classification": failure,
        "adapter_maturity": summary["maturity"],
        "live_dispatch": summary["live_dispatch"],
        "live_dispatch_available": summary["live_dispatch_available"],
        "timeout_seconds": summary["timeout_seconds"],
    }
    write_json(status_path, status_payload)
    status_sha = write_artifact_hash(base, status_rel)
    write_json(proof_path, proof_payload)
    proof_sha = write_artifact_hash(base, proof_rel)
    return {
        "schema": ADAPTER_RESULT_SCHEMA,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "model": seat.get("model") or _execution(seat).get("model") or "",
        "status": status,
        "answer_path": answer_rel if answer_sha else "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "log_path": "",
        "exit_code": exit_code,
        "failure_classification": failure,
        "required": required,
        "refs": refs,
        "sha256": {
            **({"answer": answer_sha} if answer_sha else {}),
            "status": status_sha,
            "proof": proof_sha,
        },
        "adapter": summary,
    }


def required_provider_blockers_for_round(base: Path, round_id: str, seats: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for seat in seats:
        if seat.get("required", True) is False:
            continue
        seat_id = seat.get("seat_id", "")
        status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
        answer_rel = f"answers/round-{round_id}/{seat_id}.md"
        status_path = base / status_rel
        if not status_path.exists() and (base / answer_rel).exists():
            checks.append({"check_id": f"PAD-{len(checks) + 1:03d}", "name": f"provider_required_output_{seat_id}", "status": "pass", "refs": [answer_rel]})
            continue
        if not status_path.exists():
            checks.append({"check_id": f"PAD-{len(checks) + 1:03d}", "name": f"provider_required_output_{seat_id}", "status": "fail", "refs": [status_rel]})
            blockers.append({"check": "provider_required_output", "seat_id": seat_id, "reason": "required provider status missing"})
            continue
        status = _read_status(status_path)
        if status.get("status") == "completed":
            checks.append({"check_id": f"PAD-{len(checks) + 1:03d}", "name": f"provider_required_output_{seat_id}", "status": "pass", "refs": [status_rel]})
        else:
            checks.append({"check_id": f"PAD-{len(checks) + 1:03d}", "name": f"provider_required_output_{seat_id}", "status": "fail", "refs": [status_rel]})
            blockers.append(
                {
                    "check": "provider_required_output",
                    "seat_id": seat_id,
                    "reason": status.get("failure_classification") or f"required provider status is {status.get('status')}",
                }
            )
    return checks, blockers


def existing_required_provider_failures(base: Path, seats: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    required_by_id = {str(seat.get("seat_id") or ""): seat for seat in seats if seat.get("required", True) is not False}
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for status_path in sorted((base / "logs").glob("round-*/*.status.json")):
        seat_id = status_path.stem.removesuffix(".status")
        if seat_id not in required_by_id:
            continue
        status = _read_status(status_path)
        rel = status_path.relative_to(base).as_posix()
        if status.get("status") == "completed":
            checks.append({"check_id": f"PAD-{len(checks) + 1:03d}", "name": f"provider_status_{seat_id}", "status": "pass", "refs": [rel]})
        else:
            checks.append({"check_id": f"PAD-{len(checks) + 1:03d}", "name": f"provider_status_{seat_id}", "status": "fail", "refs": [rel]})
            blockers.append(
                {
                    "check": "provider_required_failure",
                    "seat_id": seat_id,
                    "reason": status.get("failure_classification") or f"required provider status is {status.get('status')}",
                }
            )
    if not checks:
        checks.append({"check_id": "PAD-001", "name": "provider_required_failures_absent", "status": "pass", "refs": ["logs"]})
    return checks, blockers


def _read_status(path: Path) -> dict[str, Any]:
    try:
        return _read_json_object(path)
    except (OSError, ValueError):
        return {"status": "failed", "failure_classification": FAILURE_MALFORMED_OUTPUT}


def _dry_run_status_and_failure(*, summary: dict[str, Any], required: bool) -> tuple[str, str]:
    if not required:
        return "skipped", FAILURE_OPTIONAL_PROVIDER_SKIPPED
    if summary.get("live_dispatch_available") is True:
        return "failed", FAILURE_ANSWER_MISSING
    return "failed", FAILURE_UNSUPPORTED_LIVE_DISPATCH


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("status root is not an object")
    return payload


def _secret_like_execution_paths(value: Any, prefix: str = "execution") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}"
            if _secret_like_key(key_text):
                paths.append(path)
            paths.extend(_secret_like_execution_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_secret_like_execution_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str) and _secret_like_value(value):
        paths.append(prefix)
    return paths


def _execution(seat: dict[str, Any]) -> dict[str, Any]:
    execution = seat.get("execution")
    return execution if isinstance(execution, dict) else {}


def _secret_like_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in SECRET_KEY_PARTS)


def _secret_like_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in SECRET_VALUE_MARKERS)


def _safe_label(value: Any) -> str:
    text = str(value)
    for part in SECRET_KEY_PARTS:
        text = text.replace(part, "[redacted-keyword]")
        text = text.replace(part.upper(), "[redacted-keyword]")
    return text.replace("`", "'").replace("\n", " ").strip()


def _team_role_label(role: Any) -> str:
    if isinstance(role, dict):
        return str(role.get("name") or role.get("role") or role.get("agent_profile_id") or "").strip()
    return str(role).strip()
