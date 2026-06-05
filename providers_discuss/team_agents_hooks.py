from __future__ import annotations

import json
import re
import sys
from io import StringIO
from pathlib import Path
from typing import Any, TextIO

from .team_agents_defaults import DEFAULT_TEAM_AGENT_ROLES


HOOK_EVENTS = {"UserPromptSubmit", "TaskCreated", "TeammateIdle", "TaskCompleted"}
DEFAULT_TRIGGER_REGEX = r"(?i)(kdh|providers-discuss|wiki|architecture|strategy|debate|review|trade-?off|설계|아키텍처|전략|논의|토론|검토)"
DEFAULT_ROLES = DEFAULT_TEAM_AGENT_ROLES
STATUS_SCHEMA = "kdh.providers-discuss.claude-team-agents-status.v1"


def handle_dispatch(
    *,
    event: str,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    root: Path,
    trigger_mode: str,
    roles: tuple[str, ...],
    default_seat: str = "claude_team",
) -> int:
    """Always-on hook entrypoint.

    Claude settings should install this dispatcher once. It only activates when
    the hook payload mentions an existing providers-discuss run directory.
    """
    if event not in HOOK_EVENTS:
        print(f"unsupported hook event: {event}", file=stderr)
        return 2
    try:
        payload = json.loads(stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(f"malformed hook input JSON: {exc}", file=stderr)
        return 2
    context = _infer_dispatch_context(payload=payload, root=root, default_seat=default_seat)
    if context is None:
        return 0
    return handle_hook(
        event=event,
        stdin=StringIO(json.dumps(payload, ensure_ascii=False)),
        stdout=stdout,
        stderr=stderr,
        root=root,
        run_id=context["run_id"],
        round_id=context["round_id"],
        seat_id=context["seat_id"],
        trigger_mode=trigger_mode,
        trigger_regex=re.escape(context["run_id"]),
        roles=roles,
    )


def _infer_dispatch_context(*, payload: dict[str, Any], root: Path, default_seat: str) -> dict[str, str] | None:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    run_ids = _mentioned_run_ids(root=root, raw=raw)
    if len(run_ids) != 1:
        return None
    run_id = run_ids[0]
    base = root / run_id
    return {
        "run_id": run_id,
        "round_id": _infer_round_id(raw=raw, base=base),
        "seat_id": _infer_seat_id(raw=raw, default=default_seat),
    }


def _mentioned_run_ids(*, root: Path, raw: str) -> list[str]:
    if not root.exists() or not root.is_dir():
        return []
    matches = []
    for child in root.iterdir():
        if child.is_dir() and (child / "run.json").exists() and child.name in raw:
            matches.append(child.name)
    return sorted(matches)


def _infer_round_id(*, raw: str, base: Path) -> str:
    patterns = (
        r"round_id\s*[:=]\s*[`'\"]?(R\d+)",
        r"round\s*[:=]\s*[`'\"]?(R\d+)",
        r"round[-_/](R\d+)",
        r"providers-r(\d+)-",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            value = match.group(1).upper()
            return value if value.startswith("R") else f"R{value}"
    run_json = base / "run.json"
    if run_json.exists():
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        current_round = str(data.get("current_round") or "").strip().upper()
        if re.fullmatch(r"R\d+", current_round):
            return current_round
    return "R1"


def _infer_seat_id(*, raw: str, default: str) -> str:
    match = re.search(r"seat_id\s*[:=]\s*[`'\"]?([A-Za-z0-9_-]+)", raw)
    if match:
        return match.group(1)
    return default


def handle_hook(
    *,
    event: str,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    root: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: tuple[str, ...],
) -> int:
    if event not in HOOK_EVENTS:
        print(f"unsupported hook event: {event}", file=stderr)
        return 2
    if trigger_mode not in {"providers_discuss_hook", "global_hook"}:
        print(f"hook trigger_mode must be providers_discuss_hook or global_hook: {trigger_mode}", file=stderr)
        return 2
    try:
        payload = json.loads(stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(f"malformed hook input JSON: {exc}", file=stderr)
        return 2
    base = root / run_id
    if event == "UserPromptSubmit":
        return _handle_user_prompt_submit(
            payload=payload,
            stdout=stdout,
            base=base,
            run_id=run_id,
            round_id=round_id,
            seat_id=seat_id,
            trigger_mode=trigger_mode,
            trigger_regex=trigger_regex,
            roles=roles,
        )
    if not _payload_mentions_run(payload, run_id):
        return 0
    if event == "TaskCreated":
        return _handle_task_created(payload=payload, stderr=stderr, roles=roles)
    if event == "TeammateIdle":
        return _handle_teammate_idle(payload=payload, stderr=stderr, base=base, round_id=round_id, roles=roles)
    if event == "TaskCompleted":
        return _handle_task_completed(stderr=stderr, base=base, round_id=round_id, seat_id=seat_id, roles=roles)
    raise AssertionError(event)


def _handle_user_prompt_submit(
    *,
    payload: dict[str, Any],
    stdout: TextIO,
    base: Path,
    run_id: str,
    round_id: str,
    seat_id: str,
    trigger_mode: str,
    trigger_regex: str,
    roles: tuple[str, ...],
) -> int:
    prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
    if _is_team_agent_teammate_prompt(prompt, roles):
        return 0
    if not re.search(trigger_regex, prompt):
        return 0
    team_name = f"providers-{round_id.lower()}-{run_id}"
    answer_rel = f"answers/round-{round_id}/{seat_id}.md"
    status_rel = f"logs/round-{round_id}/{seat_id}.status.json"
    proof_rel = f"logs/round-{round_id}/{seat_id}.proof.json"
    bullets = [_role_bullet_rel(round_id=round_id, role=role) for role in roles]
    context = _additional_context(
        run_id=run_id,
        round_id=round_id,
        seat_id=seat_id,
        team_name=team_name,
        trigger_mode=trigger_mode,
        base=base,
        answer_rel=answer_rel,
        status_rel=status_rel,
        proof_rel=proof_rel,
        bullet_rels=bullets,
        roles=roles,
    )
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        },
        stdout,
        ensure_ascii=False,
    )
    stdout.write("\n")
    return 0


def _is_team_agent_teammate_prompt(prompt: str, roles: tuple[str, ...]) -> bool:
    stripped = prompt.lstrip()
    if stripped.startswith("<teammate-message"):
        return True
    lowered = prompt.lower()
    return any(
        f"you are the `{role.lower()}` teammate in team" in lowered
        or f"you are the `{_role_artifact_label(role)}` teammate in team" in lowered
        for role in roles
    )


def _role_artifact_label(role: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", role.strip().lower()).strip("-") or "role"


def _role_bullet_rel(*, round_id: str, role: str) -> str:
    return f"logs/round-{round_id}/{_role_artifact_label(role)}.bullet.txt"


def _additional_context(
    *,
    run_id: str,
    round_id: str,
    seat_id: str,
    team_name: str,
    trigger_mode: str,
    base: Path,
    answer_rel: str,
    status_rel: str,
    proof_rel: str,
    bullet_rels: list[str],
    roles: tuple[str, ...],
) -> str:
    marker_instruction = "the exact string formed by concatenating `KDH_CLAUDE` and `_DONE`"
    role_lines = "\n".join(f"- {role}: write `{base / rel}`" for role, rel in zip(roles, bullet_rels))
    return f"""KDH providers-discuss Team Agents hook context.

This prompt is inside a providers-discuss run and requires Team Agents before a final answer.

Run contract:
- run_id: `{run_id}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- team_name: `{team_name}`
- trigger_mode: `{trigger_mode}`
- run_root: `{base}`

Mandatory team protocol:
1. Use `TeamCreate` for team `{team_name}`.
2. Use `TaskCreate` for these roles: {", ".join(roles)}.
3. Launch each teammate with `Agent` scoped to team `{team_name}`.
4. Use `SendMessage` for at least six teammate-to-teammate messages that include run_id `{run_id}`.
5. Each teammate must write a bullet artifact:
{role_lines}
6. The lead must write the final answer to `{base / answer_rel}`.
7. The lead must write status JSON to `{base / status_rel}` using schema `{STATUS_SCHEMA}` and trigger_mode `{trigger_mode}`.
8. Do not answer directly until the files above are written. End by printing {marker_instruction}.
9. Do not impose a character or word limit. Preserve concrete evidence, paths, commands, counts, failure causes, and route-back details.

Expected proof path after runner collection: `{base / proof_rel}`.
"""


def _handle_task_created(*, payload: dict[str, Any], stderr: TextIO, roles: tuple[str, ...]) -> int:
    raw = json.dumps(payload, ensure_ascii=False).lower()
    if any(role.lower() in raw for role in roles):
        return 0
    print(
        "TaskCreated blocked: providers-discuss Team Agents task must name one required role: "
        + ", ".join(roles),
        file=stderr,
    )
    return 2


def _handle_teammate_idle(
    *,
    payload: dict[str, Any],
    stderr: TextIO,
    base: Path,
    round_id: str,
    roles: tuple[str, ...],
) -> int:
    teammate = str(payload.get("teammate_name") or payload.get("teammate") or "").strip()
    role_by_label = {_role_artifact_label(role): role for role in roles}
    role = teammate if teammate in roles else role_by_label.get(_role_artifact_label(teammate))
    if role is None:
        return 0
    bullet = base / _role_bullet_rel(round_id=round_id, role=role)
    if bullet.exists() and bullet.stat().st_size > 0:
        return 0
    print(f"TeammateIdle blocked: write required bullet artifact before idling: {bullet}", file=stderr)
    return 2


def _handle_task_completed(
    *,
    stderr: TextIO,
    base: Path,
    round_id: str,
    seat_id: str,
    roles: tuple[str, ...],
) -> int:
    required = [
        base / "answers" / f"round-{round_id}" / f"{seat_id}.md",
        base / "logs" / f"round-{round_id}" / f"{seat_id}.status.json",
        *(base / _role_bullet_rel(round_id=round_id, role=role) for role in roles),
    ]
    missing = [path for path in required if not path.exists() or path.stat().st_size == 0]
    if not missing:
        return 0
    print("TaskCompleted blocked: missing providers-discuss Team Agents artifacts:", file=stderr)
    for path in missing:
        print(f"- {path}", file=stderr)
    return 2


def _payload_mentions_run(payload: dict[str, Any], run_id: str) -> bool:
    if not run_id:
        return False
    return run_id in json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_roles(value: str) -> tuple[str, ...]:
    roles = tuple(item.strip() for item in value.split(",") if item.strip())
    return roles or DEFAULT_ROLES


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="kdh-providers-discuss-hook")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--event", choices=sorted(HOOK_EVENTS), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--round", default="R1")
    parser.add_argument("--seat", default="claude_team")
    parser.add_argument("--trigger-mode", choices=["providers_discuss_hook", "global_hook"], default="providers_discuss_hook")
    parser.add_argument("--trigger-regex", default=DEFAULT_TRIGGER_REGEX)
    parser.add_argument("--roles", default=",".join(DEFAULT_ROLES))
    args = parser.parse_args(argv)
    if args.dispatch:
        return handle_dispatch(
            event=args.event,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            root=args.root,
            trigger_mode=args.trigger_mode,
            roles=parse_roles(args.roles),
            default_seat=args.seat,
        )
    if not args.run_id:
        print("--run-id is required unless --dispatch is used", file=sys.stderr)
        return 2
    return handle_hook(
        event=args.event,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        root=args.root,
        run_id=args.run_id,
        round_id=args.round,
        seat_id=args.seat,
        trigger_mode=args.trigger_mode,
        trigger_regex=args.trigger_regex,
        roles=parse_roles(args.roles),
    )
