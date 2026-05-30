from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .artifacts import append_event, save_run, utc_now, write_artifact_hash, write_json
from .proofs import TRANSPORT_PROOF_SCHEMA, validate_transport_proof
from .provider_adapters import (
    ADAPTER_RESULT_SCHEMA,
    ADAPTER_STATUS_SCHEMA,
    FAILURE_ANSWER_MISSING,
    FAILURE_INSTALLED_NOT_LOGGED_IN,
    FAILURE_MALFORMED_OUTPUT,
    FAILURE_MISSING_CLI,
    FAILURE_PROVIDER_COMMAND_FAILED,
    FAILURE_TIMEOUT,
    adapter_summary,
    write_round_prompt,
)


COMPLETION_MARKER = "KDH_GEMINI_DONE"
DEFAULT_GEMINI_MODEL = "gemini-latest"


def run_gemini_headless_smoke(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    gemini_bin: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    if timeout_seconds < 1:
        raise ValueError("timeout-seconds must be positive")
    if not gemini_bin.exists():
        raise ValueError(f"gemini bin missing: {gemini_bin}")
    if not os.access(gemini_bin, os.X_OK):
        raise ValueError(f"gemini bin is not executable: {gemini_bin}")

    seat_id = seat["seat_id"]
    prompt_rel = f"prompts/round-{round_id}/{seat_id}.live-gemini-smoke.md"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    stdout_rel = f"logs/round-{round_id}/{seat_id}.stdout.log"
    stderr_rel = f"logs/round-{round_id}/{seat_id}.stderr.log"
    raw_json_rel = f"logs/round-{round_id}/{seat_id}.raw.json"
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}.proof.json"

    prompt = _smoke_prompt(run, round_id, seat_id, run_root=base, answer_rel=answer_rel)
    prompt_path = base / prompt_rel
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    write_artifact_hash(base, prompt_rel)
    append_event(base, "gemini_headless_smoke.prompt_written", run_id=run["run_id"], round_id=round_id, actor=seat_id, refs=[prompt_rel])

    result = _run_gemini(
        base=base,
        run=run,
        round_id=round_id,
        seat=seat,
        gemini_bin=gemini_bin,
        prompt=prompt,
        instruction="Execute the providers-discuss smoke prompt from stdin. Return a short Markdown answer ending with KDH_GEMINI_DONE.",
        mode="smoke-gemini-headless",
        timeout_seconds=timeout_seconds,
        prompt_rel=prompt_rel,
        answer_rel=answer_rel,
        stdout_rel=stdout_rel,
        stderr_rel=stderr_rel,
        raw_json_rel=raw_json_rel,
        status_rel=status_rel,
        proof_rel=proof_rel,
    )

    proof = _read_json(base / proof_rel)
    verification = validate_transport_proof(proof, base)
    run["state"] = "transport_smoke_completed" if verification["status"] == "pass" else "transport_smoke_failed"
    run["current_round"] = round_id
    run["last_transport_smoke"] = {
        "seat_id": seat_id,
        "transport": "gemini_cli",
        "proof_path": proof_rel,
        "status": verification["status"],
        "timed_out": result.get("timed_out") is True,
        "failure_classification": result.get("failure_classification", ""),
        "json_parse_status": result.get("json_parse_status", ""),
    }
    save_run(base, run)
    append_event(
        base,
        "gemini_headless_smoke.completed",
        run_id=run["run_id"],
        round_id=round_id,
        actor=seat_id,
        status=verification["status"],
        failure_classification=result.get("failure_classification", ""),
        refs=result["refs"],
    )
    _append_summary(base, round_id, seat_id, proof_rel, verification["status"], "live gemini_cli headless smoke")
    return {
        "status": verification["status"],
        "proof_path": proof_rel,
        "checks": verification["checks"],
        "blockers": verification["blockers"],
    }


def run_gemini_live_dispatch(
    *,
    base: Path,
    run: dict[str, Any],
    spec: dict[str, Any],
    seat: dict[str, Any],
    gemini_bin: Path | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    prompt_result = write_round_prompt(base=base, run=run, spec=spec, seat=seat)
    round_id = spec["round_id"]
    seat_id = seat["seat_id"]
    prompt_rel = prompt_result["refs"][0]
    answer_rel = prompt_result["answer_path"]
    stdout_rel = f"logs/round-{round_id}/{seat_id}.stdout.log"
    stderr_rel = f"logs/round-{round_id}/{seat_id}.stderr.log"
    raw_json_rel = f"logs/round-{round_id}/{seat_id}.raw.json"
    status_rel = prompt_result["status_path"]
    proof_rel = prompt_result["proof_path"]
    prompt_path = base / prompt_rel
    prompt = _with_live_marker_contract(prompt_path.read_text(encoding="utf-8"))
    prompt_path.write_text(prompt, encoding="utf-8")
    prompt_sha = write_artifact_hash(base, prompt_rel)

    if not gemini_bin or not gemini_bin.exists() or not os.access(gemini_bin, os.X_OK):
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

    return _run_gemini(
        base=base,
        run=run,
        round_id=round_id,
        seat=seat,
        gemini_bin=gemini_bin,
        prompt=prompt,
        instruction="Execute the provider-discuss prompt from stdin. Write a complete provider answer ending with KDH_GEMINI_DONE.",
        mode="live-dispatch",
        timeout_seconds=timeout_seconds,
        prompt_rel=prompt_rel,
        answer_rel=answer_rel,
        stdout_rel=stdout_rel,
        stderr_rel=stderr_rel,
        raw_json_rel=raw_json_rel,
        status_rel=status_rel,
        proof_rel=proof_rel,
        prompt_sha=prompt_sha,
    )


def _run_gemini(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    gemini_bin: Path,
    prompt: str,
    instruction: str,
    mode: str,
    timeout_seconds: int,
    prompt_rel: str,
    answer_rel: str,
    stdout_rel: str,
    stderr_rel: str,
    raw_json_rel: str,
    status_rel: str,
    proof_rel: str,
    prompt_sha: str | None = None,
) -> dict[str, Any]:
    seat_id = seat["seat_id"]
    model = _seat_model(seat)
    command = [str(gemini_bin), "--prompt", instruction, "--output-format", "json"]
    if model:
        command.extend(["--model", model])
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
        exit_code = None
        stdout = _coerce_text(exc.stdout)
        stderr = _coerce_text(exc.stderr)
    except OSError as exc:
        exit_code = None
        stderr = str(exc)

    answer_text, json_status, raw_json = _extract_answer(stdout)
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
    degraded = status == "completed" and json_status != "json_response"

    answer_path = base / answer_rel
    stdout_path = base / stdout_rel
    stderr_path = base / stderr_rel
    raw_json_path = base / raw_json_rel
    status_path = base / status_rel
    proof_path = base / proof_rel
    for path in (answer_path, stdout_path, stderr_path, raw_json_path, status_path, proof_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    stdout_path.write_text(_sanitize_provider_output(stdout), encoding="utf-8", errors="replace")
    stderr_path.write_text(_sanitize_provider_output(stderr), encoding="utf-8", errors="replace")
    stdout_sha = write_artifact_hash(base, stdout_rel)
    stderr_sha = write_artifact_hash(base, stderr_rel)

    answer_sha = ""
    if answer_text:
        answer_path.write_text(answer_text.rstrip() + "\n", encoding="utf-8")
        answer_sha = write_artifact_hash(base, answer_rel)

    raw_json_sha = ""
    if raw_json is not None:
        write_json(raw_json_path, raw_json)
        raw_json_sha = write_artifact_hash(base, raw_json_rel)

    summary = adapter_summary(seat, prompt_path=prompt_rel, answer_path=answer_rel)
    status_payload = {
        "schema": ADAPTER_STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "adapter_id": summary["adapter_id"],
        "mode": mode,
        "status": status,
        "required": seat.get("required", True) is not False,
        "answer_path": answer_rel if answer_sha else "",
        "proof_path": proof_rel,
        "stdout_path": stdout_rel,
        "stderr_path": stderr_rel,
        "raw_json_path": raw_json_rel if raw_json_sha else "",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "failure_classification": failure,
        "json_parse_status": json_status,
        "degraded": degraded,
        "model": model,
        "command": _safe_command(command),
        "started_at": started_at,
        "completed_at": utc_now(),
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }
    write_json(status_path, status_payload)
    status_sha = write_artifact_hash(base, status_rel)

    proof_payload = {
        "schema": TRANSPORT_PROOF_SCHEMA,
        "transport": "gemini_cli",
        "answer_path": answer_rel if answer_sha else "",
        "stdout_path": stdout_rel,
        "stderr_path": stderr_rel,
        "raw_json_path": raw_json_rel if raw_json_sha else "",
        "status_path": status_rel,
        "completion_marker": COMPLETION_MARKER,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "killed": timed_out,
        "blocked_reason": failure if failure in {FAILURE_INSTALLED_NOT_LOGGED_IN, FAILURE_MISSING_CLI} else "",
        "model": model,
        "output_format": "json",
        "json_parse_status": json_status,
        "degraded": degraded,
        "started_at": started_at,
        "completed_at": utc_now(),
    }
    write_json(proof_path, proof_payload)
    proof_sha = write_artifact_hash(base, proof_rel)

    refs = [prompt_rel, stdout_rel, stderr_rel, status_rel, proof_rel]
    if answer_sha:
        refs.insert(1, answer_rel)
    if raw_json_sha:
        refs.insert(-2, raw_json_rel)
    return {
        "schema": ADAPTER_RESULT_SCHEMA,
        "seat_id": seat_id,
        "provider": seat.get("provider", ""),
        "transport": seat.get("transport", ""),
        "model": model,
        "status": status,
        "answer_path": answer_rel if answer_sha else "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "log_path": stdout_rel,
        "exit_code": exit_code,
        "failure_classification": failure,
        "required": seat.get("required", True) is not False,
        "refs": refs,
        "timed_out": timed_out,
        "json_parse_status": json_status,
        "sha256": {
            "prompt": prompt_sha or write_artifact_hash(base, prompt_rel),
            **({"answer": answer_sha} if answer_sha else {}),
            "stdout": stdout_sha,
            "stderr": stderr_sha,
            **({"raw_json": raw_json_sha} if raw_json_sha else {}),
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
        "transport": seat.get("transport", ""),
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
        "command": ["gemini", "--prompt", "...", "--output-format", "json"],
        "secret_policy": "OAuth tokens, cookies, provider-home raw config, credential file bodies, and shell history are not collected or stored.",
    }
    proof_payload = {
        "schema": TRANSPORT_PROOF_SCHEMA,
        "transport": "gemini_cli",
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
        "transport": seat.get("transport", ""),
        "model": _seat_model(seat),
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


def _extract_answer(stdout: str) -> tuple[str, str, dict[str, Any] | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout, "raw_stdout_fallback", None
    if not isinstance(payload, dict):
        return stdout, "json_not_object_fallback", None
    response = payload.get("response")
    if isinstance(response, str) and response.strip():
        return response, "json_response", payload
    error = payload.get("error")
    if error:
        return "", "json_error", payload
    return stdout, "json_missing_response_fallback", payload


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
    if exit_code not in {0, None}:
        return FAILURE_PROVIDER_COMMAND_FAILED
    if not answer_text:
        return FAILURE_ANSWER_MISSING
    if not marker_in_answer:
        return FAILURE_MALFORMED_OUTPUT
    return ""


def _looks_auth_failure(text: str) -> bool:
    markers = ("auth", "login", "logged in", "credential", "api key", "apikey", "oauth", "permission")
    return any(marker in text for marker in markers)


def _with_live_marker_contract(prompt: str) -> str:
    return prompt.rstrip() + f"""

## Gemini Headless Runner Contract

The runner will extract your answer from Gemini CLI JSON field `response`.
End the answer with `{COMPLETION_MARKER}` on its own final line.
Do not modify source files or provider-home configuration.
"""


def _smoke_prompt(run: dict[str, Any], round_id: str, seat_id: str, *, run_root: Path, answer_rel: str) -> str:
    return f"""# KDH Gemini Headless Smoke Contract

This is a one-seat transport smoke for `kdh-providers-discuss`.
It is not consensus, not a full provider discussion round, and not a claim that
Gemini is configured on every machine.

Run details:
- run_id: `{run['run_id']}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- objective: {run['objective']}
- run_root: `{run_root}`
- answer_path: `{answer_rel}`

Return a short Markdown answer with:
- a statement that this is live gemini_cli headless smoke evidence;
- the run_id, round_id, and seat_id above;
- one concrete observation about the stdout JSON answer contract;
- `{COMPLETION_MARKER}` on its own final line.
"""


def _append_summary(base: Path, round_id: str, seat_id: str, proof_rel: str, status: str, evidence_type: str) -> None:
    summary_path = base / "summary.md"
    existing = summary_path.read_text(encoding="utf-8") if summary_path.exists() else "# kdh-providers-discuss Run\n"
    block = f"""

## Gemini Headless Smoke

- evidence_type: `{evidence_type}`
- status: `{status}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- proof: `{proof_rel}`
- boundary: transport proof only; not consensus and not proof that every target environment is logged in
"""
    summary_path.write_text(existing.rstrip() + block + "\n", encoding="utf-8")
    write_artifact_hash(base, "summary.md")


def _seat_model(seat: dict[str, Any]) -> str:
    execution = seat.get("execution") if isinstance(seat.get("execution"), dict) else {}
    return str(seat.get("model") or execution.get("model") or DEFAULT_GEMINI_MODEL).strip()


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
    # Do not attempt to preserve secrets that a provider CLI might echo by
    # mistake. The runner never reads credential files or environment values.
    patterns = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "OAUTH",
        "TOKEN",
        "SECRET",
        "PASSWORD",
    )
    sanitized = text
    for marker in patterns:
        sanitized = sanitized.replace(marker, f"{marker}[redacted-name]")
    return sanitized


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload
