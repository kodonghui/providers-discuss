from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .artifacts import utc_now, write_artifact_hash, write_json
from .proofs import TRANSPORT_PROOF_SCHEMA, validate_transport_proof
from .provider_adapters import (
    ADAPTER_RESULT_SCHEMA,
    ADAPTER_STATUS_SCHEMA,
    FAILURE_ANSWER_MISSING,
    FAILURE_INSTALLED_NOT_LOGGED_IN,
    FAILURE_MALFORMED_OUTPUT,
    FAILURE_MISSING_CLI,
    FAILURE_PERMISSION_PROMPT,
    FAILURE_PROVIDER_COMMAND_FAILED,
    FAILURE_TIMEOUT,
    adapter_summary,
    write_round_prompt,
)


COMPLETION_MARKER = "KDH_CODEX_DONE"


def run_codex_live_dispatch(
    *,
    base: Path,
    run: dict[str, Any],
    spec: dict[str, Any],
    seat: dict[str, Any],
    codex_bin: Path | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt_result = write_round_prompt(base=base, run=run, spec=spec, seat=seat)
    round_id = spec["round_id"]
    seat_id = seat["seat_id"]
    prompt_rel = prompt_result["refs"][0]
    answer_rel = prompt_result["answer_path"]
    stdout_rel = f"logs/round-{round_id}/{seat_id}.stdout.log"
    stderr_rel = f"logs/round-{round_id}/{seat_id}.stderr.log"
    status_rel = prompt_result["status_path"]
    proof_rel = prompt_result["proof_path"]
    prompt_path = base / prompt_rel
    prompt = _with_live_marker_contract(prompt_path.read_text(encoding="utf-8"), answer_rel=answer_rel)
    prompt_path.write_text(prompt, encoding="utf-8")
    prompt_sha = write_artifact_hash(base, prompt_rel)

    if not codex_bin or not codex_bin.exists() or not os.access(codex_bin, os.X_OK):
        return _write_missing_cli_result(
            base=base,
            run=run,
            round_id=round_id,
            seat=seat,
            timeout_seconds=timeout_seconds,
            prompt_rel=prompt_rel,
            prompt_sha=prompt_sha,
            answer_rel=answer_rel,
            status_rel=status_rel,
            proof_rel=proof_rel,
        )

    return _run_codex(
        base=base,
        run=run,
        round_id=round_id,
        seat=seat,
        codex_bin=codex_bin,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        prompt_rel=prompt_rel,
        answer_rel=answer_rel,
        stdout_rel=stdout_rel,
        stderr_rel=stderr_rel,
        status_rel=status_rel,
        proof_rel=proof_rel,
        prompt_sha=prompt_sha,
    )


def _run_codex(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    codex_bin: Path,
    prompt: str,
    timeout_seconds: int,
    prompt_rel: str,
    answer_rel: str,
    stdout_rel: str,
    stderr_rel: str,
    status_rel: str,
    proof_rel: str,
    prompt_sha: str,
) -> dict[str, Any]:
    seat_id = seat["seat_id"]
    answer_path = base / answer_rel
    stdout_path = base / stdout_rel
    stderr_path = base / stderr_rel
    status_path = base / status_rel
    proof_path = base / proof_rel
    for path in (answer_path, stdout_path, stderr_path, status_path, proof_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    command = _codex_command(codex_bin=codex_bin, seat=seat, base=base, answer_path=answer_path)
    started_at = utc_now()
    timed_out = False
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(base),
            timeout=timeout_seconds,
            env=_provider_env(),
        )
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = _coerce_text(exc.stdout)
        stderr = _coerce_text(exc.stderr)
    except OSError as exc:
        stderr = str(exc)

    stdout_path.write_text(_sanitize_provider_output(stdout), encoding="utf-8", errors="replace")
    stderr_path.write_text(_sanitize_provider_output(stderr), encoding="utf-8", errors="replace")
    stdout_sha = write_artifact_hash(base, stdout_rel)
    stderr_sha = write_artifact_hash(base, stderr_rel)

    answer_text = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
    fallback_used = False
    if not answer_text and COMPLETION_MARKER in stdout:
        answer_path.write_text(stdout.rstrip() + "\n", encoding="utf-8")
        answer_text = stdout
        fallback_used = True
    marker_in_answer = COMPLETION_MARKER in answer_text
    failure = _failure_classification(
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        answer_text=answer_text,
        marker_in_answer=marker_in_answer,
    )
    status = "completed" if not failure else "failed"
    answer_sha = write_artifact_hash(base, answer_rel) if answer_path.exists() else ""
    summary = adapter_summary(seat, prompt_path=prompt_rel, answer_path=answer_rel)
    model = str(seat.get("model") or seat.get("execution", {}).get("model") or "").strip()
    effort = str(seat.get("reasoning_effort") or seat.get("execution", {}).get("effort") or "default").strip()

    status_payload = {
        "schema": ADAPTER_STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": "codex_exec_file",
        "adapter_id": summary["adapter_id"],
        "mode": "live-dispatch",
        "status": status,
        "required": seat.get("required", True) is not False,
        "answer_path": answer_rel if answer_sha else "",
        "proof_path": proof_rel,
        "stdout_path": stdout_rel,
        "stderr_path": stderr_rel,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "failure_classification": failure,
        "model": model,
        "reasoning_effort": effort,
        "sandbox": _sandbox(seat),
        "stdout_capture_fallback_used": fallback_used,
        "command": _safe_command(command),
        "started_at": started_at,
        "completed_at": utc_now(),
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }
    write_json(status_path, status_payload)
    status_sha = write_artifact_hash(base, status_rel)

    proof_payload = {
        "schema": TRANSPORT_PROOF_SCHEMA,
        "transport": "codex_exec_file",
        "answer_path": answer_rel if answer_sha else "",
        "stdout_path": stdout_rel,
        "stderr_path": stderr_rel,
        "status_path": status_rel,
        "completion_marker": COMPLETION_MARKER,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "killed": timed_out,
        "blocked_reason": failure if failure in {FAILURE_INSTALLED_NOT_LOGGED_IN, FAILURE_MISSING_CLI, FAILURE_PERMISSION_PROMPT} else "",
        "model": model,
        "reasoning_effort": effort,
        "sandbox": _sandbox(seat),
        "stdout_capture_fallback_used": fallback_used,
        "started_at": started_at,
        "completed_at": utc_now(),
    }
    write_json(proof_path, proof_payload)
    proof_sha = write_artifact_hash(base, proof_rel)
    verification = validate_transport_proof(proof_payload, base)
    if verification["status"] != "pass" and not failure:
        failure = "proof_failed"
        status = "failed"

    refs = [prompt_rel, stdout_rel, stderr_rel, status_rel, proof_rel]
    if answer_sha:
        refs.insert(1, answer_rel)
    return {
        "schema": ADAPTER_RESULT_SCHEMA,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": "codex_exec_file",
        "model": model,
        "status": "completed" if verification["status"] == "pass" and not failure else status,
        "answer_path": answer_rel if answer_sha else "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "log_path": stdout_rel,
        "exit_code": exit_code,
        "failure_classification": "" if verification["status"] == "pass" and not failure else failure,
        "required": seat.get("required", True) is not False,
        "refs": refs,
        "timed_out": timed_out,
        "sha256": {
            "prompt": prompt_sha,
            **({"answer": answer_sha} if answer_sha else {}),
            "stdout": stdout_sha,
            "stderr": stderr_sha,
            "status": status_sha,
            "proof": proof_sha,
        },
        "adapter": summary,
    }


def _write_missing_cli_result(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    timeout_seconds: int,
    prompt_rel: str,
    prompt_sha: str,
    answer_rel: str,
    status_rel: str,
    proof_rel: str,
) -> dict[str, Any]:
    summary = adapter_summary(seat, prompt_path=prompt_rel, answer_path=answer_rel)
    status_payload = {
        "schema": ADAPTER_STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat["seat_id"],
        "provider": seat.get("provider", ""),
        "transport": "codex_exec_file",
        "adapter_id": summary["adapter_id"],
        "mode": "live-dispatch",
        "status": "failed",
        "required": seat.get("required", True) is not False,
        "answer_path": "",
        "proof_path": proof_rel,
        "exit_code": None,
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "failure_classification": FAILURE_MISSING_CLI,
    }
    proof_payload = {
        "schema": TRANSPORT_PROOF_SCHEMA,
        "transport": "codex_exec_file",
        "answer_path": "",
        "status_path": status_rel,
        "completion_marker": COMPLETION_MARKER,
        "exit_code": None,
        "timed_out": False,
        "killed": False,
        "blocked_reason": FAILURE_MISSING_CLI,
    }
    write_json(base / status_rel, status_payload)
    status_sha = write_artifact_hash(base, status_rel)
    write_json(base / proof_rel, proof_payload)
    proof_sha = write_artifact_hash(base, proof_rel)
    return {
        "schema": ADAPTER_RESULT_SCHEMA,
        "seat_id": seat["seat_id"],
        "provider": seat.get("provider", ""),
        "transport": "codex_exec_file",
        "model": seat.get("model", ""),
        "status": "failed",
        "answer_path": "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "log_path": "",
        "exit_code": None,
        "failure_classification": FAILURE_MISSING_CLI,
        "required": seat.get("required", True) is not False,
        "refs": [prompt_rel, status_rel, proof_rel],
        "sha256": {"prompt": prompt_sha, "status": status_sha, "proof": proof_sha},
        "adapter": summary,
    }


def _codex_command(*, codex_bin: Path, seat: dict[str, Any], base: Path, answer_path: Path) -> list[str]:
    model = str(seat.get("model") or seat.get("execution", {}).get("model") or "").strip()
    effort = str(seat.get("reasoning_effort") or seat.get("execution", {}).get("effort") or "").strip()
    command = [str(codex_bin), "--ask-for-approval", "never"]
    if model:
        command.extend(["-m", model])
    if effort and effort not in {"default", "manual"}:
        command.extend(["-c", f'model_reasoning_effort="{effort}"'])
    command.extend(
        [
            "exec",
            "-C",
            str(base),
            "--skip-git-repo-check",
            "-s",
            _sandbox(seat),
            "-o",
            str(answer_path),
            "-",
        ]
    )
    return command


def _sandbox(seat: dict[str, Any]) -> str:
    execution = seat.get("execution") if isinstance(seat.get("execution"), dict) else {}
    sandbox = str(execution.get("sandbox") or "workspace-write").strip()
    return sandbox if sandbox in {"read-only", "workspace-write", "danger-full-access"} else "workspace-write"


def _with_live_marker_contract(prompt: str, *, answer_rel: str) -> str:
    return prompt.rstrip() + f"""

## Codex Exec Runner Contract

The runner launches this prompt through `codex exec` and captures your final
message to `{answer_rel}` with `--output-last-message`.
Return one complete Markdown provider answer. End the final answer with
`{COMPLETION_MARKER}` on its own final line.
Do not modify runner-owned status, proof, event, hash, gate, or orchestrator
artifacts.
"""


def _failure_classification(
    *,
    exit_code: int | None,
    timed_out: bool,
    stdout: str,
    stderr: str,
    answer_text: str,
    marker_in_answer: bool,
) -> str:
    if timed_out:
        return FAILURE_TIMEOUT
    text = "\n".join([stdout, stderr]).lower()
    if exit_code not in {0, None} and _looks_auth_failure(text):
        return FAILURE_INSTALLED_NOT_LOGGED_IN
    if exit_code not in {0, None} and _looks_permission_failure(text):
        return FAILURE_PERMISSION_PROMPT
    if exit_code not in {0, None}:
        return FAILURE_PROVIDER_COMMAND_FAILED
    if not answer_text:
        return FAILURE_ANSWER_MISSING
    if not marker_in_answer:
        return FAILURE_MALFORMED_OUTPUT
    return ""


def _looks_auth_failure(text: str) -> bool:
    markers = ("auth", "login", "logged in", "credential", "api key", "apikey", "oauth")
    return any(marker in text for marker in markers)


def _looks_permission_failure(text: str) -> bool:
    markers = ("permission", "approval", "approve", "trust", "workspace")
    return any(marker in text for marker in markers)


def _provider_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "1")
    return env


def _safe_command(command: list[str]) -> list[str]:
    return [str(item) for item in command]


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _sanitize_provider_output(text: str) -> str:
    patterns = (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "OAUTH",
        "TOKEN",
        "SECRET",
        "PASSWORD",
    )
    sanitized = text
    for marker in patterns:
        sanitized = sanitized.replace(marker, f"{marker}[redacted-name]")
    return sanitized
