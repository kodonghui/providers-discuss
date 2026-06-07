from __future__ import annotations

import json
import os
import pty
import re
import select
import subprocess
import time
from pathlib import Path
from typing import Any

from .artifacts import append_event, save_run, utc_now, write_artifact_hash, write_json
from .proofs import TRANSPORT_PROOF_SCHEMA, validate_transport_proof
from .provider_adapters import (
    FAILURE_ANSWER_MISSING,
    FAILURE_MALFORMED_OUTPUT,
    FAILURE_PERMISSION_PROMPT,
    FAILURE_PROVIDER_COMMAND_FAILED,
    FAILURE_TIMEOUT,
    FAILURE_WORKSPACE_TRUST_PROMPT,
    effective_timeout_seconds,
)


COMPLETION_MARKER = "KDH_CLAUDE_DONE"
DEFAULT_CLAUDE_MODEL = "opus"
DEFAULT_CLAUDE_EFFORT = "max"
DEFAULT_CLAUDE_PERMISSION_MODE = "auto"
STATUS_SCHEMA = "kdh.providers-discuss.claude-k-status.v1"


def run_claude_k_smoke(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    claude_bin: Path,
    launch_cwd: Path | None,
    auto_trust: bool,
    timeout_seconds: int | None,
    timeout_override_reason: str = "",
) -> dict[str, Any]:
    runtime = build_claude_runtime(seat, timeout_seconds=timeout_seconds, timeout_override_reason=timeout_override_reason)
    effective_timeout = int(runtime["timeout_seconds"]["effective"])
    if not claude_bin.exists():
        raise ValueError(f"claude bin missing: {claude_bin}")
    if not os.access(claude_bin, os.X_OK):
        raise ValueError(f"claude bin is not executable: {claude_bin}")
    launch_cwd = launch_cwd or base
    if not launch_cwd.exists():
        raise ValueError(f"launch cwd missing: {launch_cwd}")
    if not launch_cwd.is_dir():
        raise ValueError(f"launch cwd is not a directory: {launch_cwd}")

    seat_id = seat["seat_id"]
    prompt_rel = f"prompts/round-{round_id}/{seat_id}.live-smoke.md"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    transcript_rel = f"logs/round-{round_id}/{seat_id}.transcript.ansi"
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}.proof.json"

    prompt_path = base / prompt_rel
    answer_path = base / answer_rel
    transcript_path = base / transcript_rel
    status_path = base / status_rel
    proof_path = base / proof_rel
    for path in (prompt_path, answer_path, transcript_path, status_path, proof_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    prompt = _smoke_prompt(
        run,
        round_id,
        seat_id,
        run_root=base,
        answer_rel=answer_rel,
        status_rel=status_rel,
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    write_artifact_hash(base, prompt_rel)
    append_event(base, "claude_k_smoke.prompt_written", run_id=run["run_id"], round_id=round_id, actor=seat_id, refs=[prompt_rel])

    started_at = utc_now()
    (
        raw,
        exit_code,
        timed_out,
        killed_before_completion,
        cleanup_after_completion,
        blocked_reason,
        trust_accepted,
    ) = _spawn_pty(
        claude_bin=claude_bin,
        run_root=base,
        launch_cwd=launch_cwd,
        prompt=prompt,
        prompt_path=prompt_path,
        answer_path=answer_path,
        status_path=status_path,
        auto_trust=auto_trust,
        timeout_seconds=effective_timeout,
        extra_env=claude_runtime_env(runtime),
    )
    transcript_path.write_text(raw, encoding="utf-8", errors="replace")
    write_artifact_hash(base, transcript_rel)

    marker_in_transcript = COMPLETION_MARKER in raw
    marker_in_answer = answer_path.exists() and COMPLETION_MARKER in answer_path.read_text(encoding="utf-8", errors="replace")
    if answer_path.exists():
        write_artifact_hash(base, answer_rel)

    if not status_path.exists():
        _write_fallback_status(
            status_path=status_path,
            run=run,
            round_id=round_id,
            seat_id=seat_id,
            started_at=started_at,
            exit_code=exit_code,
            timed_out=timed_out,
            killed_before_completion=killed_before_completion,
            blocked_reason=blocked_reason,
            marker_in_transcript=marker_in_transcript,
            marker_in_answer=marker_in_answer,
            auto_trust=auto_trust,
            trust_accepted=trust_accepted,
            runtime=runtime,
        )
    if status_path.exists():
        augment_status_with_runtime(status_path, runtime)
        write_artifact_hash(base, status_rel)

    proof: dict[str, Any] = {
        "schema": TRANSPORT_PROOF_SCHEMA,
        "transport": "claude_k",
        "answer_path": answer_rel,
        "transcript_path": transcript_rel,
        "status_path": status_rel,
        "completion_marker": COMPLETION_MARKER,
        "launch_cwd": str(launch_cwd),
        "runtime": claude_runtime_metadata(runtime),
        "workspace_trust_auto_accept_enabled": auto_trust,
        "workspace_trust_auto_accepted": trust_accepted,
        "timed_out": timed_out,
        "killed": killed_before_completion,
        "cleanup_after_completion": cleanup_after_completion,
        "blocked_reason": blocked_reason,
        "started_at": started_at,
        "completed_at": utc_now(),
    }
    if exit_code is not None and not cleanup_after_completion:
        proof["exit_code"] = exit_code
    if exit_code is not None and cleanup_after_completion:
        proof["exit_code_after_completion_cleanup"] = exit_code
    write_json(proof_path, proof)
    write_artifact_hash(base, proof_rel)

    result = validate_transport_proof(proof, base)
    run["state"] = "transport_smoke_completed" if result["status"] == "pass" else "transport_smoke_failed"
    run["current_round"] = round_id
    run["last_transport_smoke"] = {
        "seat_id": seat_id,
        "proof_path": proof_rel,
        "status": result["status"],
        "timed_out": timed_out,
        "killed": killed_before_completion,
        "blocked_reason": blocked_reason,
        "workspace_trust_auto_accepted": trust_accepted,
    }
    save_run(base, run)
    append_event(
        base,
        "claude_k_smoke.completed",
        run_id=run["run_id"],
        round_id=round_id,
        actor=seat_id,
        status=result["status"],
        timed_out=timed_out,
        killed=killed_before_completion,
        blocked_reason=blocked_reason,
        refs=[answer_rel, transcript_rel, status_rel, proof_rel],
    )
    _append_summary(base, round_id, seat_id, proof_rel, result["status"])
    return {
        "status": result["status"],
        "proof_path": proof_rel,
        "runtime": claude_runtime_metadata(runtime),
        "checks": result["checks"],
        "blockers": result["blockers"],
    }


def build_claude_runtime(seat: dict[str, Any], *, timeout_seconds: int | None, timeout_override_reason: str = "") -> dict[str, Any]:
    execution = seat.get("execution") if isinstance(seat.get("execution"), dict) else {}
    selected_model = _runtime_text(seat.get("model") or execution.get("model") or DEFAULT_CLAUDE_MODEL)
    selected_effort = _runtime_text(seat.get("reasoning_effort") or execution.get("effort") or DEFAULT_CLAUDE_EFFORT)
    selected_permission_mode = _runtime_text(execution.get("permission_mode") or DEFAULT_CLAUDE_PERMISSION_MODE)
    selected_timeout = effective_timeout_seconds(seat)
    effective_timeout = timeout_seconds if timeout_seconds is not None else selected_timeout
    if effective_timeout < 1:
        raise ValueError("timeout-seconds must be positive")
    timeout_overridden = timeout_seconds is not None and effective_timeout != selected_timeout
    reason = timeout_override_reason.strip()
    if timeout_overridden and not reason:
        raise ValueError(
            "timeout override requires --override-reason; "
            f"selected timeout_seconds={selected_timeout}, requested={effective_timeout}"
        )
    return {
        "model": {"selected": selected_model, "effective": selected_model, "overridden": False, "override_reason": ""},
        "effort": {"selected": selected_effort, "effective": selected_effort, "overridden": False, "override_reason": ""},
        "permission_mode": {
            "selected": selected_permission_mode,
            "effective": selected_permission_mode,
            "overridden": False,
            "override_reason": "",
        },
        "timeout_seconds": {
            "selected": selected_timeout,
            "effective": effective_timeout,
            "overridden": timeout_overridden,
            "override_reason": reason if timeout_overridden else "",
        },
    }


def claude_runtime_env(runtime: dict[str, Any]) -> dict[str, str]:
    return {
        "KDH_PROVIDER_DISCUSS_CLAUDE_MODEL": str(runtime["model"]["effective"]),
        "KDH_PROVIDER_DISCUSS_CLAUDE_EFFORT": str(runtime["effort"]["effective"]),
        "KDH_PROVIDER_DISCUSS_CLAUDE_PERMISSION_MODE": str(runtime["permission_mode"]["effective"]),
    }


def claude_runtime_metadata(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": dict(runtime["model"]),
        "effort": dict(runtime["effort"]),
        "permission_mode": dict(runtime["permission_mode"]),
        "timeout_seconds": dict(runtime["timeout_seconds"]),
    }


def augment_status_with_runtime(status_path: Path, runtime: dict[str, Any]) -> None:
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    payload["runtime"] = claude_runtime_metadata(runtime)
    write_json(status_path, payload)


def _runtime_text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "default"


def _spawn_pty(
    *,
    claude_bin: Path,
    run_root: Path,
    launch_cwd: Path,
    prompt: str,
    prompt_path: Path | None,
    answer_path: Path,
    status_path: Path,
    auto_trust: bool,
    timeout_seconds: int,
    extra_env: dict[str, str] | None = None,
    drop_env_keys: tuple[str, ...] = (),
) -> tuple[str, int | None, bool, bool, bool, str, bool]:
    master_fd, slave_fd = pty.openpty()
    env = os.environ.copy()
    for key in drop_env_keys:
        env.pop(key, None)
    env.update(
        {
            "KDH_PROVIDER_DISCUSS_RUN_ROOT": str(run_root),
            "KDH_PROVIDER_DISCUSS_LAUNCH_CWD": str(launch_cwd),
            "KDH_PROVIDER_DISCUSS_ANSWER_PATH": str(answer_path),
            "KDH_PROVIDER_DISCUSS_STATUS_PATH": str(status_path),
            "KDH_PROVIDER_DISCUSS_COMPLETION_MARKER": COMPLETION_MARKER,
        }
    )
    if extra_env:
        env.update(extra_env)
    command = [
        str(claude_bin),
        "--model",
        env.get("KDH_PROVIDER_DISCUSS_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
        "--effort",
        env.get("KDH_PROVIDER_DISCUSS_CLAUDE_EFFORT", DEFAULT_CLAUDE_EFFORT),
        "--permission-mode",
        env.get("KDH_PROVIDER_DISCUSS_CLAUDE_PERMISSION_MODE", DEFAULT_CLAUDE_PERMISSION_MODE),
    ]
    if not _is_relative_to(run_root.resolve(), launch_cwd.resolve()):
        command.extend(["--add-dir", str(run_root)])
    launcher_prompt = _launcher_prompt(prompt_path=prompt_path, fallback_prompt=prompt)
    proc = subprocess.Popen(
        command,
        cwd=str(launch_cwd),
        env=env,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    chunks: list[str] = []
    try:
        os.write(master_fd, f"{launcher_prompt}\r".encode("utf-8"))
        chunks.append("\n[KDH_PTY_ACTION prompt-submitted]\n")
    except OSError:
        chunks.append("\n[KDH_PTY_ACTION prompt-submit-failed]\n")
    timed_out = False
    killed_before_completion = False
    cleanup_after_completion = False
    completion_seen = False
    blocked_reason = ""
    trust_accepted = False
    exit_sent = False
    cleanup_deadline: float | None = None
    deadline = time.monotonic() + timeout_seconds

    try:
        while True:
            now = time.monotonic()
            if now > deadline and not completion_seen:
                timed_out = True
                killed_before_completion = True
                _terminate_process(proc)
                break
            if cleanup_deadline is not None and now > cleanup_deadline and proc.poll() is None:
                cleanup_after_completion = True
                _terminate_process(proc)
                break
            if not completion_seen and _artifact_completion_seen(answer_path=answer_path):
                completion_seen = True
                if proc.poll() is None and not exit_sent:
                    try:
                        os.write(master_fd, b"\n/exit\n")
                        exit_sent = True
                        cleanup_deadline = time.monotonic() + 5
                    except OSError:
                        cleanup_after_completion = True
                        _terminate_process(proc)
                        break

            readable, _, _ = select.select([master_fd], [], [], 0.2)
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    data = b""
                if not data:
                    if proc.poll() is not None:
                        break
                else:
                    for response in _terminal_query_responses(data):
                        os.write(master_fd, response)
                    chunk = data.decode("utf-8", errors="replace")
                    chunks.append(chunk)
                    if not completion_seen:
                        blocked_reason = _detect_blocking_prompt("".join(chunks))
                        if blocked_reason == "workspace_trust_prompt" and auto_trust and not trust_accepted:
                            try:
                                os.write(master_fd, b"1\r")
                                trust_accepted = True
                                chunks.append("\n[KDH_PTY_ACTION workspace-trust-1-enter]\n")
                                blocked_reason = ""
                                continue
                            except OSError:
                                blocked_reason = "workspace_trust_auto_accept_failed"
                        if blocked_reason == "workspace_trust_prompt" and trust_accepted:
                            blocked_reason = ""
                            continue
                        if blocked_reason:
                            killed_before_completion = True
                            _terminate_process(proc)
                            break
                    if COMPLETION_MARKER in "".join(chunks) and not completion_seen:
                        completion_seen = True
                        if proc.poll() is None and not exit_sent:
                            try:
                                os.write(master_fd, b"\n/exit\n")
                                exit_sent = True
                                cleanup_deadline = time.monotonic() + 5
                            except OSError:
                                cleanup_after_completion = True
                                _terminate_process(proc)
                                break

            if proc.poll() is not None:
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    try:
        exit_code = proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _terminate_process(proc)
        exit_code = proc.poll()
    return "".join(chunks), exit_code, timed_out, killed_before_completion, cleanup_after_completion, blocked_reason, trust_accepted


def _launcher_prompt(*, prompt_path: Path | None, fallback_prompt: str) -> str:
    if prompt_path is None:
        return fallback_prompt
    return (
        "Read and execute the instructions in this prompt file exactly: "
        f"{prompt_path.resolve()}. Write the required artifacts before final response."
    )


def _artifact_completion_seen(*, answer_path: Path) -> bool:
    try:
        return COMPLETION_MARKER in answer_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


def _terminal_query_responses(data: bytes, *, cols: int = 120, rows: int = 40) -> list[bytes]:
    responses: list[bytes] = []
    if b"\x1b[c" in data or b"\x1b[0c" in data:
        responses.append(b"\x1b[?62;22c")
    if b"\x1b[>c" in data or b"\x1b[>0c" in data:
        responses.append(b"\x1b[>1;1;0c")
    if b"\x1b[6n" in data:
        responses.append(b"\x1b[1;1R")
    if b"\x1b[>q" in data:
        responses.append(b"\x1bP>|kdh-pty 0\x1b\\")
    if b"\x1b[18t" in data:
        responses.append(f"\x1b[8;{rows};{cols}t".encode("ascii"))
    return responses


def _detect_blocking_prompt(text: str) -> str:
    clean = _strip_ansi(text)
    compact = "".join(ch.lower() for ch in clean if ch.isalnum())
    if "quicksafetycheck" in compact and "trust" in compact and "folder" in compact:
        return "workspace_trust_prompt"
    if "allowexternal" in compact and "externalimports" in compact:
        return "external_imports_prompt"
    if "bypasspermissionsmode" in compact:
        return "bypass_permissions_prompt"
    return ""


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|P[^\x1b]*(?:\x1b\\))", "", text)


def _write_fallback_status(
    *,
    status_path: Path,
    run: dict[str, Any],
    round_id: str,
    seat_id: str,
    started_at: str,
    exit_code: int | None,
    timed_out: bool,
    killed_before_completion: bool,
    blocked_reason: str,
    marker_in_transcript: bool,
    marker_in_answer: bool,
    auto_trust: bool,
    trust_accepted: bool,
    runtime: dict[str, Any],
) -> None:
    if blocked_reason:
        verdict = "failed"
    elif timed_out:
        verdict = "timeout"
    elif exit_code not in {0, None}:
        verdict = "failed"
    elif marker_in_transcript and marker_in_answer:
        verdict = "admitted"
    else:
        verdict = "failed"
    failure_classification = _failure_classification(
        verdict=verdict,
        blocked_reason=blocked_reason,
        exit_code=exit_code,
        timed_out=timed_out,
        marker_in_transcript=marker_in_transcript,
        marker_in_answer=marker_in_answer,
    )
    write_json(
        status_path,
        {
            "schema": STATUS_SCHEMA,
            "run_id": run["run_id"],
            "round_id": round_id,
            "seat_id": seat_id,
            "verdict": verdict,
            "started_at": started_at,
            "completed_at": utc_now(),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "killed_before_completion": killed_before_completion,
            "blocked_reason": blocked_reason,
            "failure_classification": failure_classification,
            "marker_in_transcript": marker_in_transcript,
            "marker_in_answer": marker_in_answer,
            "workspace_trust_auto_accept_enabled": auto_trust,
            "workspace_trust_auto_accepted": trust_accepted,
            "runtime": claude_runtime_metadata(runtime),
        },
    )


def _failure_classification(
    *,
    verdict: str,
    blocked_reason: str,
    exit_code: int | None,
    timed_out: bool,
    marker_in_transcript: bool,
    marker_in_answer: bool,
) -> str:
    if verdict == "admitted":
        return ""
    if blocked_reason == FAILURE_WORKSPACE_TRUST_PROMPT:
        return FAILURE_WORKSPACE_TRUST_PROMPT
    if blocked_reason:
        return FAILURE_PERMISSION_PROMPT
    if timed_out:
        return FAILURE_TIMEOUT
    if exit_code not in {0, None}:
        return FAILURE_PROVIDER_COMMAND_FAILED
    if not marker_in_answer:
        return FAILURE_ANSWER_MISSING
    if not marker_in_transcript:
        return FAILURE_MALFORMED_OUTPUT
    return FAILURE_MALFORMED_OUTPUT


def _smoke_prompt(
    run: dict[str, Any],
    round_id: str,
    seat_id: str,
    *,
    run_root: Path,
    answer_rel: str,
    status_rel: str,
) -> str:
    answer_abs = run_root / answer_rel
    status_abs = run_root / status_rel
    marker_instruction = "the exact string formed by concatenating `KDH_CLAUDE` and `_DONE`"
    return f"""# KDH Claude-K Live Smoke Contract

This is a one-seat transport smoke for `kdh-providers-discuss`.
It is not Team Agents proof, not consensus, and not live 5R automation.

Run details:
- run_id: `{run['run_id']}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- objective: {run['objective']}
- run_root: `{run_root}`

Write the answer file at `{answer_abs}`. Include:
- a short statement that this is live claude_k transport smoke evidence;
- the run_id, round_id, and seat_id above;
- one concrete observation about the file contract;
- the completion marker, {marker_instruction}, on its own final line.

Write status JSON at `{status_abs}` with this shape:

```json
{{
  "schema": "{STATUS_SCHEMA}",
  "run_id": "{run['run_id']}",
  "round_id": "{round_id}",
  "seat_id": "{seat_id}",
  "verdict": "admitted",
  "timed_out": false
}}
```

After both files are written, print that same completion marker to the terminal.
Do not use `claude -p`. Do not modify source files or provider-home config.
"""


def _append_summary(base: Path, round_id: str, seat_id: str, proof_rel: str, status: str) -> None:
    summary_path = base / "summary.md"
    existing = summary_path.read_text(encoding="utf-8") if summary_path.exists() else "# kdh-providers-discuss Run\n"
    block = f"""

## Claude-K Live Smoke

- evidence_type: `live claude_k transport smoke`
- status: `{status}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- proof: `{proof_rel}`
- boundary: transport proof only; not Team Agents proof, not consensus, not live 5R automation
"""
    summary_path.write_text(existing.rstrip() + block + "\n", encoding="utf-8")
    write_artifact_hash(base, "summary.md")
