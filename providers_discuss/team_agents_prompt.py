from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final


TEAM_AGENTS_STATUS_SCHEMA: Final = "kdh.providers-discuss.claude-team-agents-status.v1"


def team_agents_prompt(
    *,
    run: Mapping[str, str],
    round_id: str,
    seat_id: str,
    team_name: str,
    teammates: Sequence[str],
    required_direct_messages: int,
    run_root: Path,
    answer_rel: str,
    status_rel: str,
    trigger_mode: str,
    include_provider_result: bool,
) -> str:
    answer_abs = run_root / answer_rel
    status_abs = run_root / status_rel
    marker_instruction = "the exact string formed by concatenating `KDH_CLAUDE` and `_DONE`"
    teammate_count = len(teammates)
    teammate_list = format_teammate_list(teammates)
    run_context = run_context_section(round_id=round_id, run_root=run_root, include_provider_result=include_provider_result)
    answer_contract = answer_contract_section(include_provider_result=include_provider_result)
    return f"""# KDH Claude-K Team Agents Live Smoke Contract

This is a bounded Team Agents PoC inside a live Claude Code PTY session.
It must use real Team Agents behavior. Summary-only delegation is a failure.

Run details:
- run_id: `{run['run_id']}`
- round_id: `{round_id}`
- seat_id: `{seat_id}`
- objective: {run['objective']}
- run_root: `{run_root}`
- team_name: `{team_name}`
- teammates: {", ".join(teammates)}
- required_direct_messages: {required_direct_messages}
- trigger_mode: `{trigger_mode}`

{run_context}

Required live actions:
1. Use `TeamCreate` to create the named team above.
2. Use `TaskCreate` to create one teammate task for each required teammate above:
   {teammate_list}.
3. Launch each teammate through the team-scoped tool named `Agent`, using the
   team name above as the team scope.
4. Use `SendMessage` for at least {required_direct_messages}
   teammate-to-teammate messages. Include the run_id and `test: hi` in each
   message token.
5. If the Team Agents surface is unavailable, write status JSON with
   `blocked_reason: "team_agents_surface_missing"` and do not claim success.

Write the answer file at `{answer_abs}`. Include:
{answer_contract}
- the completion marker, {marker_instruction}, on its own final line.

Write status JSON at `{status_abs}` with this shape:

```json
{{
  "schema": "{TEAM_AGENTS_STATUS_SCHEMA}",
  "run_id": "{run['run_id']}",
  "round_id": "{round_id}",
  "seat_id": "{seat_id}",
  "team_name": "{team_name}",
  "trigger_mode": "{trigger_mode}",
  "verdict": "admitted",
  "timed_out": false,
  "team_create_used": true,
  "task_create_count": {teammate_count},
  "agent_calls_with_team_name": {teammate_count},
  "direct_teammate_messages_required": {required_direct_messages},
  "direct_teammate_messages_observed": {required_direct_messages},
  "ordinary_agent_delegation_only": false,
  "summary_only_delegation": false,
  "blocked_reason": ""
}}
```

After both files are written, print that same completion marker to the terminal.
Do not use `claude -p`. Do not modify source files or provider-home config.
"""


def run_context_section(*, round_id: str, run_root: Path, include_provider_result: bool) -> str:
    context_refs: list[str] = []
    for rel in (
        "inputs/input-pack.md",
        "config/source-index.json",
        "config/providers-discuss.config.json",
    ):
        if (run_root / rel).exists():
            context_refs.append(rel)
    delta_rel = f"prompts/round-{round_id}.prompt-delta.md"
    if (run_root / delta_rel).exists():
        context_refs.append(delta_rel)
    for path in sorted((run_root / "answers").glob("round-R*/*.md")):
        rel = path.relative_to(run_root).as_posix()
        if rel not in context_refs:
            context_refs.append(rel)
    for folder in ("gates", "orchestrator"):
        folder_path = run_root / folder
        if not folder_path.exists():
            continue
        for path in sorted(folder_path.glob("*.md")):
            rel = path.relative_to(run_root).as_posix()
            if rel not in context_refs:
                context_refs.append(rel)
    if not context_refs:
        return "Input/context files: none attached yet."
    lines = [
        "Input/context files:",
        f"- run_root: `{run_root}`",
    ]
    lines.extend(f"- `{rel}`" for rel in context_refs)
    if include_provider_result:
        lines.extend(
            [
                "",
                "Before writing the answer, have teammates read the relevant input pack/source index and prior-round artifacts listed above.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "This is proof-only smoke. Do not read the input pack deeply and do not write a curriculum/provider answer.",
                "Use short `test: hi` acknowledgements to prove team creation, team-scoped work, and direct messages.",
            ]
        )
    return "\n".join(lines)


def answer_contract_section(*, include_provider_result: bool) -> str:
    lines = [
        "- a short statement that this is live claude_k Team Agents smoke evidence;",
        "- the run_id, round_id, seat_id, and team_name above;",
        "- a `test_outputs` section with one short `test: hi` bullet from each teammate;",
        "- the direct message tokens used;",
    ]
    if include_provider_result:
        lines.extend(
            [
                "- a substantive answer section after `test_outputs` that follows the round task, includes",
                "  source support, and ends with `## Claims For Gate`;",
            ]
        )
    else:
        lines.append("- no curriculum, provider conclusion, claim map, or source synthesis;")
    return "\n".join(lines)


def format_teammate_list(teammates: Sequence[str]) -> str:
    if not teammates:
        return ""
    if len(teammates) == 1:
        return teammates[0]
    if len(teammates) == 2:
        return f"{teammates[0]} and {teammates[1]}"
    return f"{', '.join(teammates[:-1])}, and {teammates[-1]}"
