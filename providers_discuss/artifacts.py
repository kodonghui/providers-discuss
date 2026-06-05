from __future__ import annotations

import hashlib
import json
import random
import shutil
import string
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is expected on the target Linux runtime.
    fcntl = None  # type: ignore[assignment]


RUN_SCHEMA = "kdh.providers-discuss.run.v1"
EVENT_SCHEMA = "kdh.providers-discuss.event.v1"
VERIFY_SCHEMA = "kdh.providers-discuss.verify.v1"
CLAIM_MAP_SCHEMA = "kdh.providers-discuss.claim-map.v1"
GATE_SCHEMA = "kdh.providers-discuss.gate.v1"
PROVIDER_SEATS_SCHEMA = "kdh.providers-discuss.provider-seats.v1"
SOURCE_INDEX_SCHEMA = "kdh.providers-discuss.source-index.v1"

HARNESS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = HARNESS_ROOT / ".kdh" / "kdh-providers-discuss"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 2400
DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT = 6
DEFAULT_OPENAI_CODEX_MODEL: Final = "gpt-5.5"
DEFAULT_OPENAI_MODEL_SELECTION: Final = "latest_available_via_official_docs_or_cli_discovery"
DEFAULT_OPENAI_REASONING_EFFORT: Final = "xhigh"
DEFAULT_CLAUDE_CODE_MODEL: Final = "opus"
DEFAULT_CLAUDE_MODEL_SELECTION: Final = "claude_code_latest_opus_alias"
DEFAULT_CLAUDE_REASONING_EFFORT: Final = "max"

ALLOWED_STATES = {
    "created",
    "preflight_ready",
    "preflight_passed",
    "round_prompt_ready",
    "round_running",
    "round_outputs_collected",
    "round_verified",
    "round_gated",
    "transport_smoke_completed",
    "transport_smoke_failed",
    "team_agents_smoke_completed",
    "team_agents_smoke_failed",
    "orchestrator_reviewed",
    "next_round_ready",
    "finalizing",
    "finished",
    "failed",
    "cancelled",
    "interrupted",
    "stop_for_CEO_alignment",
}

ALLOWED_CLAIM_STATUSES = {
    "supported",
    "unsupported",
    "contested",
    "deferred",
    "rejected",
    "superseded",
}

ALLOWED_GATE_VERDICTS = {
    "proceed_to_next_round",
    "proceed_to_final",
    "proceed_to_implementation",
    "return_to_round",
    "return_to_preflight",
    "return_to_design",
    "stop_for_CEO_alignment",
    "failed_runtime",
    "cancelled",
}

ROUND_PLANS: dict[str, tuple[dict[str, str], ...]] = {
    "two-seat-3r": (
        {"round_id": "R1", "mode": "explore", "title": "Independent ideas and risk candidates"},
        {"round_id": "R2", "mode": "challenge", "title": "Challenge weak claims and missing evidence"},
        {"round_id": "R3", "mode": "decide", "title": "Accepted, rejected, deferred contract"},
    ),
    "two-seat-5r": (
        {"round_id": "R1", "mode": "explore", "title": "Source alignment and idea extraction"},
        {"round_id": "R2", "mode": "challenge", "title": "Overreach, hidden runtime, framework challenge"},
        {"round_id": "R3", "mode": "synthesize", "title": "Transport, artifact, schema candidates"},
        {"round_id": "R4", "mode": "verify", "title": "Failure simulation and recovery requirements"},
        {"round_id": "R5", "mode": "decide", "title": "Terminal decision and implementation gate"},
    ),
    "trio-3r": (
        {"round_id": "R1", "mode": "explore", "title": "Independent ideas and risk candidates"},
        {"round_id": "R2", "mode": "challenge", "title": "Challenge weak claims and missing evidence"},
        {"round_id": "R3", "mode": "decide", "title": "Accepted, rejected, deferred contract"},
    ),
    "duo-team-5r": (
        {"round_id": "R1", "mode": "explore", "title": "Source alignment and idea extraction"},
        {"round_id": "R2", "mode": "challenge", "title": "Overreach, hidden runtime, framework challenge"},
        {"round_id": "R3", "mode": "synthesize", "title": "Transport, artifact, schema candidates"},
        {"round_id": "R4", "mode": "verify", "title": "Failure simulation and recovery requirements"},
        {"round_id": "R5", "mode": "decide", "title": "Terminal decision and implementation gate"},
    ),
    "trio-5r": (
        {"round_id": "R1", "mode": "explore", "title": "Independent proposals"},
        {"round_id": "R2", "mode": "challenge", "title": "Conflicts and missing evidence"},
        {"round_id": "R3", "mode": "synthesize", "title": "Architecture candidates"},
        {"round_id": "R4", "mode": "verify", "title": "Failure simulation and tests"},
        {"round_id": "R5", "mode": "decide", "title": "Implementation contract"},
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d-%H%M%S")
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"{stamp}-{suffix}"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_root(root: Path, run_id: str) -> Path:
    return root / run_id


def ensure_run_dirs(base: Path) -> None:
    for rel in (
        "config",
        "prompts",
        "answers",
        "logs",
        "claims",
        "gates",
        "orchestrator",
        "final",
        "hashes",
    ):
        (base / rel).mkdir(parents=True, exist_ok=True)


def provider_seats_for_preset(preset: str) -> dict[str, Any]:
    if preset in {"duo-team-5r", "two-seat-3r", "two-seat-5r"}:
        seats = [
            {
                "seat_id": "gpt",
                "provider": "openai",
                "transport": "codex_exec_file",
                "model": DEFAULT_OPENAI_CODEX_MODEL,
                "model_selection": DEFAULT_OPENAI_MODEL_SELECTION,
                "reasoning_effort": DEFAULT_OPENAI_REASONING_EFFORT,
                "role": "ideation, contradiction search, verifier, overengineering check",
                "required": True,
                "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
                "execution": {
                    "sandbox": "workspace-write",
                    "model": DEFAULT_OPENAI_CODEX_MODEL,
                    "model_selection": DEFAULT_OPENAI_MODEL_SELECTION,
                    "effort": DEFAULT_OPENAI_REASONING_EFFORT,
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
                "model": DEFAULT_CLAUDE_CODE_MODEL,
                "model_selection": DEFAULT_CLAUDE_MODEL_SELECTION,
                "reasoning_effort": DEFAULT_CLAUDE_REASONING_EFFORT,
                "role": "team-based ideation, source synthesis, architecture critique, QA verification",
                "required": True,
                "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
                "execution": {
                    "model": DEFAULT_CLAUDE_CODE_MODEL,
                    "model_selection": DEFAULT_CLAUDE_MODEL_SELECTION,
                    "effort": DEFAULT_CLAUDE_REASONING_EFFORT,
                    "permission_mode": "auto",
                },
                "team_agents": {
                    "enabled": True,
                    "required_teammates": ["Ideation Catalyst", "Research Synthesizer", "System Architect", "QA Verifier"],
                    "required_direct_message_count": DEFAULT_TEAM_AGENTS_DIRECT_MESSAGE_COUNT,
                },
            },
        ]
        topology = "two-seat-team-agents"
    elif preset == "trio-5r":
        seats = _trio_seats()
        topology = "trio"
    elif preset == "trio-3r":
        seats = _trio_seats()
        topology = "trio"
    else:
        raise ValueError(f"unknown preset: {preset}")
    return {"schema": PROVIDER_SEATS_SCHEMA, "topology": topology, "preset": preset, "seats": seats}


def _trio_seats() -> list[dict[str, Any]]:
    return [
        {
            "seat_id": "gpt",
            "provider": "openai",
            "transport": "codex_exec_file",
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
            "seat_id": "claude_a",
            "provider": "anthropic",
            "transport": "claude_k",
            "role": "independent ideation and architecture proposal",
            "required": True,
            "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        },
        {
            "seat_id": "claude_b",
            "provider": "anthropic",
            "transport": "claude_k",
            "role": "alternative design and edge-case critique",
            "required": True,
            "timeout_seconds": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        },
    ]


def load_run(base: Path) -> dict[str, Any]:
    return read_json(base / "run.json")


def save_run(base: Path, run: dict[str, Any]) -> None:
    state = run.get("state")
    if state not in ALLOWED_STATES:
        raise ValueError(f"invalid run state: {state}")
    run["updated_at"] = utc_now()
    write_json(base / "run.json", run)


def append_event(base: Path, event_type: str, **fields: Any) -> dict[str, Any]:
    path = base / "events.jsonl"
    with _file_lock(base / ".locks" / "events.lock"):
        seq = 1
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                seq = sum(1 for line in fh if line.strip()) + 1
        event = {
            "schema": EVENT_SCHEMA,
            "event_id": f"EVT-{seq:04d}",
            "seq": seq,
            "ts": utc_now(),
            "type": event_type,
            **fields,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event


def read_events(base: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with (base / "events.jsonl").open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"events.jsonl:{line_no}: invalid JSONL: {exc}") from exc
    return events


def required_seats(base: Path) -> list[dict[str, Any]]:
    return [seat for seat in provider_seats(base) if seat.get("required", True)]


def provider_seats(base: Path) -> list[dict[str, Any]]:
    config = read_json(base / "config" / "provider-seats.json")
    return list(config.get("seats", []))


def round_spec(run: dict[str, Any], round_id: str) -> dict[str, Any]:
    for item in run.get("rounds", []):
        if item.get("round_id") == round_id:
            return item
    raise ValueError(f"unknown round: {round_id}")


def next_round_id(run: dict[str, Any], round_id: str) -> str:
    rounds = [item["round_id"] for item in run.get("rounds", [])]
    if round_id not in rounds:
        raise ValueError(f"unknown round: {round_id}")
    index = rounds.index(round_id)
    if index + 1 >= len(rounds):
        return ""
    return rounds[index + 1]


def write_artifact_hash(base: Path, rel_path: str) -> str:
    path = base / rel_path
    digest = sha256_file(path)
    hash_path = base / "hashes" / "artifacts.sha256.json"
    with _file_lock(base / ".locks" / "hashes.lock"):
        data = read_json(hash_path) if hash_path.exists() else {"schema": "kdh.providers-discuss.artifact-hashes.v1", "artifacts": {}}
        data["artifacts"][rel_path] = digest
        write_json(hash_path, data)
    append_event(base, "artifact.hashed", refs=[rel_path], sha256=digest)
    return digest


@contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def copy_answer(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
