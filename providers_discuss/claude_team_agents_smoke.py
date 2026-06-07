from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT, append_event, save_run, utc_now, write_artifact_hash, write_json
from .claude_smoke import (
    COMPLETION_MARKER,
    _spawn_pty,
    augment_status_with_runtime,
    build_claude_runtime,
    claude_runtime_env,
    claude_runtime_metadata,
)
from .agent_profiles import team_role_specs
from .proofs import TEAM_AGENTS_PROOF_SCHEMA, validate_team_agents_proof
from .provider_adapters import FAILURE_PERMISSION_PROMPT, FAILURE_PROOF_FAILED, FAILURE_TIMEOUT, FAILURE_WORKSPACE_TRUST_PROMPT
from .team_agents_prompt import team_agents_prompt


STATUS_SCHEMA = "kdh.providers-discuss.claude-team-agents-status.v1"


def run_claude_team_agents_smoke(
    *,
    base: Path,
    run: dict[str, Any],
    round_id: str,
    seat: dict[str, Any],
    claude_bin: Path,
    launch_cwd: Path | None,
    auto_trust: bool,
    experimental_agent_teams: bool,
    timeout_seconds: int | None,
    trigger_mode: str,
    timeout_override_reason: str = "",
    provider_result_artifacts: bool = False,
) -> dict[str, Any]:
    runtime = build_claude_runtime(seat, timeout_seconds=timeout_seconds, timeout_override_reason=timeout_override_reason)
    if not provider_result_artifacts:
        _bound_smoke_runtime(runtime)
    effective_timeout = int(runtime["timeout_seconds"]["effective"])
    if not claude_bin.exists():
        raise ValueError(f"claude bin missing: {claude_bin}")
    if not os.access(claude_bin, os.X_OK):
        raise ValueError(f"claude bin is not executable: {claude_bin}")
    launch_cwd = (launch_cwd or base).resolve()
    if not launch_cwd.exists():
        raise ValueError(f"launch cwd missing: {launch_cwd}")
    if not launch_cwd.is_dir():
        raise ValueError(f"launch cwd is not a directory: {launch_cwd}")
    if trigger_mode not in {"prompt_only", "providers_discuss_hook", "global_hook"}:
        raise ValueError(f"unsupported trigger-mode: {trigger_mode}")

    seat_id = seat["seat_id"]
    team_cfg = seat.get("team_agents") if isinstance(seat.get("team_agents"), dict) else {}
    teammates = [role["name"] for role in team_role_specs(team_cfg)]
    required_direct_messages = int(team_cfg.get("required_direct_message_count", DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT))
    team_name = f"providers-{round_id.lower()}-{run['run_id']}"

    prompt_suffix = "live-team-agents" if provider_result_artifacts else "live-team-agents-smoke"
    artifact_suffix = "" if provider_result_artifacts else ".team-agents-smoke"
    prompt_rel = f"prompts/round-{round_id}/{seat_id}.{prompt_suffix}.md"
    answer_rel = f"answers/round-{round_id}/{seat_id}{artifact_suffix}.md"
    transcript_rel = f"logs/round-{round_id}/{seat_id}.transcript.ansi"
    status_rel = f"logs/round-{round_id}/{seat_id}{artifact_suffix}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}{artifact_suffix}.proof.json"
    session_jsonl_dir_rel = f"logs/round-{round_id}/session-jsonl"
    team_state_dir_rel = f"logs/round-{round_id}/team-state"

    prompt_path = base / prompt_rel
    answer_path = base / answer_rel
    transcript_path = base / transcript_rel
    status_path = base / status_rel
    proof_path = base / proof_rel
    session_jsonl_dir = base / session_jsonl_dir_rel
    team_state_dir = base / team_state_dir_rel
    for path in (prompt_path, answer_path, transcript_path, status_path, proof_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    session_jsonl_dir.mkdir(parents=True, exist_ok=True)
    team_state_dir.mkdir(parents=True, exist_ok=True)
    if not provider_result_artifacts:
        _clear_stale_smoke_artifacts(
            paths=[answer_path, transcript_path, status_path, proof_path, _proof_verify_path(proof_path)],
            dirs=[session_jsonl_dir, team_state_dir],
        )

    prompt = team_agents_prompt(
        run=run,
        round_id=round_id,
        seat_id=seat_id,
        team_name=team_name,
        teammates=teammates,
        required_direct_messages=required_direct_messages,
        run_root=base.resolve(),
        answer_rel=answer_rel,
        status_rel=status_rel,
        trigger_mode=trigger_mode,
        include_provider_result=provider_result_artifacts,
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    write_artifact_hash(base, prompt_rel)
    append_event(base, "claude_team_agents_smoke.prompt_written", run_id=run["run_id"], round_id=round_id, actor=seat_id, refs=[prompt_rel])

    started_at = utc_now()
    before_jsonl = _snapshot_claude_jsonl()
    before_tmux_panes = _snapshot_tmux_panes()
    started_epoch = time.time()
    extra_env = {
        **claude_runtime_env(runtime),
        "KDH_PROVIDER_DISCUSS_TEAM_NAME": team_name,
        "KDH_PROVIDER_DISCUSS_SESSION_JSONL_DIR": str(session_jsonl_dir),
        "KDH_PROVIDER_DISCUSS_TEAM_STATE_DIR": str(team_state_dir),
    }
    if experimental_agent_teams:
        extra_env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
    cleanup_report: dict[str, Any] = {}
    try:
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
            run_root=base.resolve(),
            launch_cwd=launch_cwd,
            prompt=prompt,
            prompt_path=prompt_path,
            answer_path=answer_path.resolve(),
            status_path=status_path.resolve(),
            auto_trust=auto_trust,
            timeout_seconds=effective_timeout,
            extra_env=extra_env,
            drop_env_keys=("TMUX", "TMUX_PANE"),
        )
    finally:
        cleanup_report = _cleanup_team_runtime(team_name=team_name, before_tmux_panes=before_tmux_panes, launch_cwd=launch_cwd)
    transcript_path.write_text(raw, encoding="utf-8", errors="replace")
    write_artifact_hash(base, transcript_rel)
    if answer_path.exists():
        write_artifact_hash(base, answer_rel)

    session_jsonl_rels = _collect_session_jsonl(
        base=base,
        dest_dir=session_jsonl_dir,
        dest_rel=session_jsonl_dir_rel,
        before=before_jsonl,
        run_id=run["run_id"],
        team_name=team_name,
        started_epoch=started_epoch,
    )
    team_state_rels = _collect_team_state(base=base, dest_dir=team_state_dir, dest_rel=team_state_dir_rel, team_name=team_name)
    for rel in session_jsonl_rels + team_state_rels:
        write_artifact_hash(base, rel)

    status = _load_status(status_path)
    if not status:
        status = _fallback_status(
            run=run,
            round_id=round_id,
            seat_id=seat_id,
            team_name=team_name,
            started_at=started_at,
            exit_code=exit_code,
            timed_out=timed_out,
            killed_before_completion=killed_before_completion,
            blocked_reason=blocked_reason,
            required_direct_messages=required_direct_messages,
            raw="\n".join([raw, _read_rel_files(base, session_jsonl_rels)]),
        )
        write_json(status_path, status)
    augment_status_with_runtime(status_path, runtime)
    status = _load_status(status_path) or status

    session_tool_counts = _session_tool_counts(base, session_jsonl_rels, team_name)
    status = _recover_missing_status_from_session_evidence(
        status,
        session_tool_counts=session_tool_counts,
        required_teammates=teammates,
        required_direct_messages=required_direct_messages,
        status_path=status_path,
        answer_path=answer_path,
    )
    proof = _build_proof(
        status=status,
        team_name=team_name,
        required_teammates=teammates,
        required_direct_messages=required_direct_messages,
        session_tool_counts=session_tool_counts,
        status_rel=status_rel,
        transcript_rel=transcript_rel,
        session_jsonl_rels=session_jsonl_rels,
        team_state_rels=team_state_rels,
        blocked_reason=blocked_reason,
        timed_out=timed_out,
        killed=killed_before_completion,
        cleanup_after_completion=cleanup_after_completion,
        trust_accepted=trust_accepted,
        experimental_agent_teams=experimental_agent_teams,
        tmux_env_stripped=True,
        cleanup_report=cleanup_report,
        launch_cwd=launch_cwd,
        started_at=started_at,
        trigger_mode=trigger_mode,
        runtime=runtime,
        process_exit_code=exit_code,
    )
    result = validate_team_agents_proof(proof, base)
    proof_passed = result["status"] == "pass"
    _write_provider_status_fields(
        status_path=status_path,
        status=status,
        provider_status="completed" if proof_passed else "failed",
        answer_rel=answer_rel if answer_path.exists() else "",
        proof_rel=proof_rel,
        mode="live-dispatch" if provider_result_artifacts else "smoke-claude-team-agents",
        failure_classification="" if proof_passed else _team_agents_failure(result["blockers"]),
        process_exit_code=exit_code,
        proof_passed=proof_passed,
    )
    write_artifact_hash(base, status_rel)
    write_json(proof_path, proof)
    write_artifact_hash(base, proof_rel)

    run["state"] = "team_agents_smoke_completed" if result["status"] == "pass" else "team_agents_smoke_failed"
    run["current_round"] = round_id
    run["last_team_agents_smoke"] = {
        "seat_id": seat_id,
        "proof_path": proof_rel,
        "status": result["status"],
        "team_name": team_name,
        "trigger_mode": trigger_mode,
        "timed_out": timed_out,
        "killed": killed_before_completion,
        "blocked_reason": proof.get("blocked_reason") or blocked_reason,
        "workspace_trust_auto_accepted": trust_accepted,
        "experimental_agent_teams_enabled": experimental_agent_teams,
        "tmux_env_stripped": True,
        "team_runtime_cleanup": cleanup_report,
        "runtime": claude_runtime_metadata(runtime),
    }
    save_run(base, run)
    append_event(
        base,
        "claude_team_agents_smoke.completed",
        run_id=run["run_id"],
        round_id=round_id,
        actor=seat_id,
        status=result["status"],
        timed_out=timed_out,
        killed=killed_before_completion,
        blocked_reason=proof.get("blocked_reason") or blocked_reason,
        trigger_mode=trigger_mode,
        experimental_agent_teams_enabled=experimental_agent_teams,
        tmux_env_stripped=True,
        team_runtime_cleanup=cleanup_report,
        runtime=claude_runtime_metadata(runtime),
        refs=[answer_rel, transcript_rel, status_rel, proof_rel],
    )
    _append_summary(base, round_id, seat_id, team_name, proof_rel, result["status"], trigger_mode)
    return {
        "status": result["status"],
        "answer_path": answer_rel if answer_path.exists() else "",
        "status_path": status_rel,
        "proof_path": proof_rel,
        "team_name": team_name,
        "trigger_mode": trigger_mode,
        "experimental_agent_teams_enabled": experimental_agent_teams,
        "tmux_env_stripped": True,
        "team_runtime_cleanup": cleanup_report,
        "runtime": claude_runtime_metadata(runtime),
        "checks": result["checks"],
        "blockers": result["blockers"],
    }


def _clear_stale_smoke_artifacts(*, paths: list[Path], dirs: list[Path]) -> None:
    for path in paths:
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
        except OSError:
            pass
    for directory in dirs:
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)


def _proof_verify_path(proof_path: Path) -> Path:
    if proof_path.name.endswith(".proof.json"):
        return proof_path.with_name(proof_path.name[: -len(".proof.json")] + ".proof.verify.json")
    return proof_path.with_name(f"{proof_path.name}.verify.json")


def _bound_smoke_runtime(runtime: dict[str, Any]) -> None:
    effort = runtime.get("effort")
    if not isinstance(effort, dict):
        return
    if effort.get("effective") == "medium":
        return
    effort["effective"] = "medium"
    effort["overridden"] = True
    effort["override_reason"] = "proof-only Team Agents smoke uses bounded reasoning effort"


def _write_provider_status_fields(
    *,
    status_path: Path,
    status: dict[str, Any],
    provider_status: str,
    answer_rel: str,
    proof_rel: str,
    mode: str,
    failure_classification: str,
    process_exit_code: int | None,
    proof_passed: bool,
) -> None:
    payload = dict(status)
    provider_exit_code, cleanup_exit_code, cleanup_signal = _provider_cleanup_exit_codes(
        process_exit_code=process_exit_code,
        proof_passed=proof_passed,
    )
    payload["status"] = provider_status
    payload["answer_path"] = answer_rel
    payload["proof_path"] = proof_rel
    payload["mode"] = mode
    payload["failure_classification"] = failure_classification
    payload["process_exit_code"] = process_exit_code
    payload["provider_exit_code"] = provider_exit_code
    payload["cleanup_exit_code"] = cleanup_exit_code
    payload["cleanup_signal"] = cleanup_signal
    payload["cleanup_warning"] = cleanup_exit_code is not None
    payload["exit_code"] = provider_exit_code
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    if isinstance(runtime.get("model"), dict):
        payload["model"] = runtime["model"].get("effective", "")
    if isinstance(runtime.get("effort"), dict):
        payload["reasoning_effort"] = runtime["effort"].get("effective", "")
    if isinstance(runtime.get("permission_mode"), dict):
        payload["permission_mode"] = runtime["permission_mode"].get("effective", "")
    if isinstance(runtime.get("timeout_seconds"), dict):
        payload["timeout_seconds"] = runtime["timeout_seconds"].get("effective", payload.get("timeout_seconds"))
    write_json(status_path, payload)


def _provider_cleanup_exit_codes(*, process_exit_code: int | None, proof_passed: bool) -> tuple[int | None, int | None, str]:
    if proof_passed and process_exit_code not in (None, 0):
        cleanup_signal = "SIGTERM" if process_exit_code in {143, -15} else ""
        return 0, process_exit_code, cleanup_signal
    return process_exit_code, None, ""


def _team_agents_failure(blockers: list[dict[str, Any]]) -> str:
    for blocker in blockers:
        reason = str(blocker.get("reason") or "")
        if reason:
            return f"{FAILURE_PROOF_FAILED}:{reason}"
    return FAILURE_PROOF_FAILED


def _snapshot_claude_jsonl() -> dict[Path, int]:
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return {}
    snapshot: dict[Path, int] = {}
    for path in root.rglob("*.jsonl"):
        try:
            snapshot[path] = path.stat().st_mtime_ns
        except OSError:
            continue
    return snapshot


def _snapshot_tmux_panes() -> dict[str, dict[str, str]]:
    if not shutil.which("tmux"):
        return {}
    result = subprocess.run(
        ["tmux", "list-panes", "-a", "-F", "#{pane_id}\t#{pane_pid}\t#{pane_current_path}\t#{pane_current_command}"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return {}
    panes: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        pane_id, pane_pid, cwd, command = (line.split("\t", 3) + ["", "", "", ""])[:4]
        if pane_id:
            panes[pane_id] = {"pane_pid": pane_pid, "cwd": cwd, "command": command}
    return panes


def _cleanup_team_runtime(*, team_name: str, before_tmux_panes: dict[str, dict[str, str]], launch_cwd: Path) -> dict[str, Any]:
    return {
        "killed_process_pids": _kill_team_processes(team_name),
        "killed_tmux_panes": _kill_new_tmux_panes(before_tmux_panes, launch_cwd),
    }


def _kill_team_processes(team_name: str) -> list[int]:
    if not team_name:
        return []
    result = subprocess.run(
        ["pgrep", "-af", team_name],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode not in {0, 1}:
        return []
    own_pids = {os.getpid(), os.getppid()}
    candidates: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[1] if len(parts) > 1 else ""
        if pid in own_pids or "pgrep -af" in command:
            continue
        candidates.append(pid)

    killed: list[int] = []
    for pid in candidates:
        if _terminate_pid(pid, signal.SIGTERM):
            killed.append(pid)
    time.sleep(0.2)
    for pid in candidates:
        if _pid_alive(pid):
            _terminate_pid(pid, signal.SIGKILL)
    return killed


def _terminate_pid(pid: int, sig: signal.Signals) -> bool:
    try:
        os.kill(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _kill_new_tmux_panes(before_tmux_panes: dict[str, dict[str, str]], launch_cwd: Path) -> list[str]:
    if not before_tmux_panes:
        return []
    after = _snapshot_tmux_panes()
    launch_cwd_text = str(launch_cwd)
    killed: list[str] = []
    for pane_id, pane in after.items():
        if pane_id in before_tmux_panes:
            continue
        command = pane.get("command", "")
        cwd = pane.get("cwd", "")
        if cwd != launch_cwd_text and "claude" not in command:
            continue
        result = subprocess.run(["tmux", "kill-pane", "-t", pane_id], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            killed.append(pane_id)
    return killed


def _collect_session_jsonl(
    *,
    base: Path,
    dest_dir: Path,
    dest_rel: str,
    before: dict[Path, int],
    run_id: str,
    team_name: str,
    started_epoch: float,
) -> list[str]:
    root = Path.home() / ".claude" / "projects"
    if root.exists():
        for path in root.rglob("*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if before.get(path) == stat.st_mtime_ns and stat.st_mtime < started_epoch:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if run_id not in text and team_name not in text:
                continue
            target = dest_dir / _safe_jsonl_name(root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    rels = _relative_files(base, dest_dir)
    return [rel for rel in rels if rel.endswith(".jsonl")]


def _collect_team_state(*, base: Path, dest_dir: Path, dest_rel: str, team_name: str) -> list[str]:
    source = Path.home() / ".claude" / "teams" / team_name
    if source.exists():
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(source)
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    return _relative_files(base, dest_dir)


def _safe_jsonl_name(root: Path, path: Path) -> Path:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    safe = "__".join(rel.parts)
    return Path(safe)


def _relative_files(base: Path, directory: Path) -> list[str]:
    rels: list[str] = []
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            rels.append(str(path.relative_to(base)))
    return rels


def _load_status(status_path: Path) -> dict[str, Any]:
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _fallback_status(
    *,
    run: dict[str, Any],
    round_id: str,
    seat_id: str,
    team_name: str,
    started_at: str,
    exit_code: int | None,
    timed_out: bool,
    killed_before_completion: bool,
    blocked_reason: str,
    required_direct_messages: int,
    raw: str,
) -> dict[str, Any]:
    raw_team_create = "TeamCreate" in raw
    raw_agent_count = _count_team_scoped_agent_markers(raw, team_name)
    raw_messages = _count_marker_lines(raw, ["SendMessage"])
    verdict = "failed"
    if timed_out:
        verdict = "timeout"
    failure_classification = FAILURE_TIMEOUT if timed_out else _team_failure_classification(blocked_reason)
    return {
        "schema": STATUS_SCHEMA,
        "run_id": run["run_id"],
        "round_id": round_id,
        "seat_id": seat_id,
        "team_name": team_name,
        "verdict": verdict,
        "started_at": started_at,
        "completed_at": utc_now(),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "killed_before_completion": killed_before_completion,
        "blocked_reason": blocked_reason or "status_json_missing",
        "failure_classification": failure_classification,
        "team_create_used": raw_team_create,
        "task_create_count": _count_marker_lines(raw, ["TaskCreate"]),
        "agent_calls_with_team_name": raw_agent_count,
        "direct_teammate_messages_required": required_direct_messages,
        "direct_teammate_messages_observed": raw_messages,
        "ordinary_agent_delegation_only": True,
        "summary_only_delegation": True,
    }


def _team_failure_classification(blocked_reason: str) -> str:
    if blocked_reason == FAILURE_WORKSPACE_TRUST_PROMPT:
        return FAILURE_WORKSPACE_TRUST_PROMPT
    if blocked_reason:
        return FAILURE_PERMISSION_PROMPT
    return FAILURE_PROOF_FAILED


def _recover_missing_status_from_session_evidence(
    status: dict[str, Any],
    *,
    session_tool_counts: dict[str, int],
    required_teammates: list[str],
    required_direct_messages: int,
    status_path: Path,
    answer_path: Path,
) -> dict[str, Any]:
    if status.get("blocked_reason") != "status_json_missing":
        return status
    if not answer_path.exists():
        return status
    try:
        answer_text = answer_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return status
    if COMPLETION_MARKER not in answer_text:
        return status
    required_tasks = len(required_teammates)
    required_agents = len(required_teammates)
    if session_tool_counts["team_create"] < 1:
        return status
    if session_tool_counts["task_create"] < required_tasks:
        return status
    if session_tool_counts["agent_with_team_name"] < required_agents:
        return status
    if session_tool_counts["send_message"] < required_direct_messages:
        return status

    recovered = dict(status)
    recovered.update(
        {
            "verdict": "admitted",
            "blocked_reason": "",
            "failure_classification": "",
            "status": "completed",
            "team_create_used": True,
            "task_create_count": max(_int(status.get("task_create_count")), session_tool_counts["task_create"]),
            "agent_calls_with_team_name": max(_int(status.get("agent_calls_with_team_name")), session_tool_counts["agent_with_team_name"]),
            "direct_teammate_messages_required": _int(status.get("direct_teammate_messages_required")) or required_direct_messages,
            "direct_teammate_messages_observed": max(
                _int(status.get("direct_teammate_messages_observed")),
                session_tool_counts["send_message"],
            ),
            "ordinary_agent_delegation_only": False,
            "summary_only_delegation": False,
            "status_json_missing_recovered_from_session_jsonl": True,
        }
    )
    write_json(status_path, recovered)
    return recovered


def _build_proof(
    *,
    status: dict[str, Any],
    team_name: str,
    required_teammates: list[str],
    required_direct_messages: int,
    session_tool_counts: dict[str, int],
    status_rel: str,
    transcript_rel: str,
    session_jsonl_rels: list[str],
    team_state_rels: list[str],
    blocked_reason: str,
    timed_out: bool,
    killed: bool,
    cleanup_after_completion: bool,
    trust_accepted: bool,
    experimental_agent_teams: bool,
    tmux_env_stripped: bool,
    cleanup_report: dict[str, Any],
    launch_cwd: Path,
    started_at: str,
    trigger_mode: str,
    runtime: dict[str, Any],
    process_exit_code: int | None,
) -> dict[str, Any]:
    proof_shape_passed = not bool(status.get("blocked_reason") or blocked_reason or timed_out or killed)
    provider_exit_code, cleanup_exit_code, cleanup_signal = _provider_cleanup_exit_codes(
        process_exit_code=process_exit_code,
        proof_passed=proof_shape_passed,
    )
    return {
        "schema": TEAM_AGENTS_PROOF_SCHEMA,
        "transport": "claude_k_team_agents",
        "trigger_mode": str(status.get("trigger_mode") or trigger_mode),
        "team_create_used": bool(status.get("team_create_used")) or session_tool_counts["team_create"] >= 1,
        "team_state_equivalent_count": session_tool_counts["team_state_equivalent"],
        "team_name": str(status.get("team_name") or team_name),
        "required_teammates": required_teammates,
        "required_task_count": len(required_teammates),
        "task_create_count": max(_int(status.get("task_create_count")), session_tool_counts["task_create"]),
        "required_team_scoped_agent_calls": len(required_teammates),
        "agent_calls_with_team_name": max(_int(status.get("agent_calls_with_team_name")), session_tool_counts["agent_with_team_name"]),
        "direct_teammate_messages_required": _int(status.get("direct_teammate_messages_required")) or required_direct_messages,
        "direct_teammate_messages_observed": max(_int(status.get("direct_teammate_messages_observed")), session_tool_counts["send_message"]),
        "ordinary_agent_delegation_only": status.get("ordinary_agent_delegation_only", False),
        "summary_only_delegation": status.get("summary_only_delegation", False),
        "blocked_reason": status.get("blocked_reason") or blocked_reason,
        "process_exit_code": process_exit_code,
        "provider_exit_code": provider_exit_code,
        "cleanup_exit_code": cleanup_exit_code,
        "cleanup_signal": cleanup_signal,
        "timed_out": timed_out,
        "killed": killed,
        "cleanup_after_completion": cleanup_after_completion,
        "workspace_trust_auto_accepted": trust_accepted,
        "experimental_agent_teams_enabled": experimental_agent_teams,
        "tmux_env_stripped": tmux_env_stripped,
        "team_runtime_cleanup": cleanup_report,
        "launch_cwd": str(launch_cwd),
        "runtime": claude_runtime_metadata(runtime),
        "started_at": started_at,
        "completed_at": utc_now(),
        "artifacts": {
            "status": status_rel,
            "transcript": transcript_rel,
            "session_jsonl": session_jsonl_rels,
            "team_state": team_state_rels,
        },
    }


def _read_rel_files(base: Path, rels: list[str]) -> str:
    chunks: list[str] = []
    for rel in rels:
        path = base / rel
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _session_tool_counts(base: Path, rels: list[str], team_name: str) -> dict[str, int]:
    counts = {
        "team_create": 0,
        "team_state_equivalent": 0,
        "task_create": 0,
        "agent_with_team_name": 0,
        "send_message": 0,
    }
    for rel in rels:
        path = base / rel
        if not path.exists():
            continue
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


def _count_marker_lines(text: str, markers: list[str]) -> int:
    count = 0
    for line in text.splitlines():
        if any(marker in line for marker in markers):
            count += 1
    return count


def _count_team_scoped_agent_markers(text: str, team_name: str) -> int:
    team_pattern = re.compile(rf"team[_-]?name\s*[:=]\s*['\"]?{re.escape(team_name)}['\"]?")
    count = 0
    for line in text.splitlines():
        if "Agent" in line and team_pattern.search(line):
            count += 1
    return count


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _append_summary(base: Path, round_id: str, seat_id: str, team_name: str, proof_rel: str, status: str, trigger_mode: str = "prompt_only") -> None:
    summary_path = base / "summary.md"
    existing = summary_path.read_text(encoding="utf-8") if summary_path.exists() else "# kdh-providers-discuss Run\n"
    block = "\n".join(
        [
            "## Claude-K Team Agents Smoke",
            "",
            "- evidence_type: `live claude_k_team_agents smoke`",
            f"- status: `{status}`",
            f"- round_id: `{round_id}`",
            f"- seat_id: `{seat_id}`",
            f"- team_name: `{team_name}`",
            f"- trigger_mode: `{trigger_mode}`",
            f"- proof: `{proof_rel}`",
            "- boundary: PoC proof only; not normal runner promotion",
            "",
        ]
    )
    existing = _remove_existing_summary_blocks(existing, round_id=round_id, seat_id=seat_id, proof_rel=proof_rel)
    summary_path.write_text(existing.rstrip() + "\n\n" + block, encoding="utf-8")
    write_artifact_hash(base, "summary.md")


def _remove_existing_summary_blocks(existing: str, *, round_id: str, seat_id: str, proof_rel: str) -> str:
    lines = existing.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index] != "## Claude-K Team Agents Smoke":
            output.append(lines[index])
            index += 1
            continue
        end = index + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1
        block = lines[index:end]
        block_text = "\n".join(block)
        same_seat = f"- round_id: `{round_id}`" in block_text and f"- seat_id: `{seat_id}`" in block_text
        same_proof = f"- proof: `{proof_rel}`" in block_text
        if not (same_seat or same_proof):
            output.extend(block)
        index = end
    return "\n".join(output).rstrip() + "\n"
