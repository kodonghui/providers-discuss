# providers-discuss

`providers-discuss` is a file-backed discussion runner for comparing outputs
from multiple AI provider seats. It records prompts, answers, status files,
proof files, gates, hashes, and orchestrator prompt deltas on disk so a run can
be inspected without trusting chat scrollback.

This repository is an early public staging package for
`kodonghui/providers-discuss`. The manual/import workflow and artifact
contract are the safest current path. Live provider adapters are still marked
by their maturity level below.

## What It Is

- A local CLI for configuring dynamic rounds and provider seats.
- A runner that writes observable artifacts under a run directory.
- A manual/import workflow that works without live provider credentials.
- A provider adapter shell for Codex, Claude, Claude Team Agents, Gemini, and
  manual seats.
- A proof-gated Team Agents workflow that can generate a prompt-only contract
  and explain proof pass/fail results.
- A read-only agent profile catalog gate for assigning prompt-only roles to
  provider seats or Claude Team Agents teammates.

## What It Is Not

- It is not a hidden provider automation daemon.
- It is not a vector database, memory system, or RAG server.
- It does not collect OAuth tokens, cookies, browser state, shell history, or
  provider-home raw config.
- It does not execute BMAD, oh-my-agents, KDH agent framework scripts, or any
  third-party agent runtime from a catalog.
- It does not currently provide polished live dispatch for Codex, Gemini, or
  normal multiround Claude Team Agents.
- It does not treat dry-run previews, fake proof fixtures, or summary-only Team
  Agents output as live provider success.

## Install

From this directory:

```bash
./install.sh --dry-run
./install.sh
providers-discuss --help
```

The installer creates local links for:

- `$HOME/.local/bin/providers-discuss`
- `$HOME/.codex/skills/providers-discuss`
- `$HOME/.codex/skills/kdh-providers-discuss`

It does not modify provider settings or install hooks. Restart Codex after
installing so both skill names are loaded. `providers-discuss` is the public
skill name; `kdh-providers-discuss` is a compatibility alias for KDH workflows.

Uninstall:

```bash
./install.sh --uninstall
```

You can also run without installing:

```bash
bin/providers-discuss --help
```

## Quick Start: Manual Import

Manual import is the safest first workflow because it proves the artifact
contract without live provider credentials.

```bash
work="$(mktemp -d)"
cp examples/minimal-manual.config.json "$work/providers-discuss.config.json"

bin/providers-discuss validate-config "$work/providers-discuss.config.json"
run_id="$(bin/providers-discuss init --config "$work/providers-discuss.config.json" --root "$work/runs" --run-id manual-demo | tail -n 1)"
bin/providers-discuss preflight "$run_id" --root "$work/runs"
bin/providers-discuss run-round "$run_id" --root "$work/runs" --round R1 --mode dry-run

cat > "$work/manual-answer.md" <<'EOF'
# Manual answer

The manual seat recommends keeping every decision tied to artifacts.
EOF

bin/providers-discuss run-round "$run_id" --root "$work/runs" --round R1 --mode manual-import --answer human_reviewer="$work/manual-answer.md"

python3 - "$work/runs/$run_id" <<'PY'
import json, sys
from pathlib import Path
run = Path(sys.argv[1])
(run / "claims").mkdir(exist_ok=True)
(run / "claims" / "round-R1-claim-map.json").write_text(json.dumps({
  "schema": "kdh.providers-discuss.claim-map.v1",
  "run_id": run.name,
  "round_id": "R1",
  "claims": [{
    "claim_id": "CLM-R1-001",
    "claim": "Manual import can preserve provider evidence as files.",
    "claim_type": "decision",
    "status": "supported",
    "load_bearing": False,
    "support": ["answers/round-R1/human_reviewer.md"]
  }]
}, indent=2) + "\n")
PY

bin/providers-discuss gate "$run_id" --root "$work/runs" --round R1
bin/providers-discuss orchestrate "$run_id" --root "$work/runs" --after-round R1
bin/providers-discuss verify "$run_id" --root "$work/runs"
```

Important run artifacts:

- `run.json`
- `events.jsonl`
- `config/provider-seats.json`
- `prompts/round-Rn/*.prompt.md`
- `answers/round-Rn/*.md`
- `logs/round-Rn/*.status.json`
- `logs/round-Rn/*.proof.json`
- `claims/round-Rn-claim-map.json`
- `gates/round-Rn-gate.md`
- `orchestrator/round-Rn-review.md`
- `verify.json`

## Dynamic Config

Use `config-template` for a starting point:

```bash
bin/providers-discuss config-template --output providers-discuss.config.json
bin/providers-discuss validate-config providers-discuss.config.json --json
```

Each config contains:

- `language`
- `objective`
- `brainstorming`
- `input.source_dirs`
- `rounds`
- `seats`
- provider, transport, model, reasoning effort, timeout, and required/optional
  flags
- optional Team Agents roles and direct-message requirements

Examples:

- `examples/minimal-manual.config.json`
- `examples/codex-claude.config.json`
- `examples/claude-team-agents.config.json`
- `examples/gemini-optional.config.json`
- `examples/profile-balanced-kdh.config.json`

For user-facing setup, follow the staged intake workflow in
`docs/intake-workflow.md`: language, rounds, seats, providers/efforts, agent
profiles, topic, brainstorming mode, and input data path.

## Agent Profiles

Agent profiles are prompt-only role contracts. They can shape a provider seat
or a Claude Team Agents teammate, but they do not grant tools, credentials,
hooks, filesystem permissions, or provider-home access.

List profiles before choosing them:

```bash
bin/providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json
bin/providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json --seat human_reviewer --markdown
bin/providers-discuss agent-profiles --catalog examples/agents/kdh-mini-catalog.json --transport manual
```

Use `agent_profile_id` per seat or enable `agent_profile_defaults` with
`balanced-kdh`. Normal reports show clean user-facing fields such as id, name,
description, provider targets, Team Agents fit, source profile count, catalog
reference, and compatibility. They do not dump source profile ids or local
source repository paths.

## Auth/Login Gate

`auth-preflight` checks selected enabled seats before live work:

```bash
bin/providers-discuss auth-preflight examples/codex-claude.config.json --report-dir auth-report
```

The report is sanitized. It records readiness classes such as
`installed_logged_in`, `installed_not_logged_in`, `missing_cli`, and
`manual_or_skipped`, plus a next action. It must not copy OAuth tokens, cookies,
provider-home config bodies, or shell history.

## Input Folder Packaging

`build-input-pack` scans declared source folders and writes deterministic local
file artifacts:

```bash
bin/providers-discuss build-input-pack --config providers-discuss.config.json --output-dir input-pack
```

The builder records paths, hashes, headings, bounded excerpts, and omission
reasons. It is not RAG, embeddings, GraphRAG, Obsidian, wiki generation, web
research, or LLM summarization.

## Provider Maturity

| Adapter | Transport | Current maturity | Live dispatch |
|---|---|---|---|
| manual_import | manual | live | manual-import |
| codex_exec_file | codex_exec_file | structural | not polished public live dispatch |
| claude_code | claude_k | smoke_only | smoke-claude-k only |
| claude_team_agents | claude_k_team_agents | smoke_only | smoke-claude-team-agents plus proof verifier |
| gemini_cli | gemini_cli | placeholder | not implemented |

Use `adapter-capabilities` to inspect the current truth:

```bash
bin/providers-discuss adapter-capabilities --config examples/claude-team-agents.config.json --json
```

## Claude Team Agents

Prompt-only path:

```bash
bin/providers-discuss team-agents-prompt <run-id> --root <runs> --round R1 --seat claude_team --json
```

This writes `prompts/round-R1/claude_team.team-agents-prompt.md`. It does not
launch Claude and does not install hooks.

Proof-report path:

```bash
bin/providers-discuss team-agents-proof-report <run-id> --root <runs> --proof logs/round-R1/claude_team.proof.json --json
```

Summary-only delegation, ordinary subagents, or proof without durable Team
Agents evidence must fail.

Hook-assisted paths are explicit:

```bash
bin/providers-discuss hook-config --run-id <run-id> --root <runs> --json
bin/providers-discuss hook-config --run-id <run-id> --root <runs> --repair --json
bin/providers-discuss hook-config --run-id <run-id> --root <runs> --remove --json
bin/providers-discuss runtime-preflight --workspace "$PWD" --root <runs> --run-id <run-id> --trigger-mode prompt_only --json
```

`prompt_only` does not require hook config. Hook-assisted modes fail closed
until explicitly installed.

## Troubleshooting

- `validate-config` fails: check `schema`, duplicate seat ids, provider/transport
  pairing, and Team Agents role count.
- `auth-preflight` blocks: required provider credentials are not ready. Log in
  with the provider's official CLI or mark that seat optional/disabled.
- `manual-import` fails: every required enabled seat needs a matching
  `--answer seat_id=/path/to/file.md`.
- `gate` returns `return_to_round`: add or fix the claim map, provider answer,
  or support evidence.
- `verify` fails: inspect `verify.json`; the blocker names the missing artifact
  or failed provider status.

## Release Status

This repository is public early-stage work. `RELEASE-CHECKLIST.md` still tracks
the gates for a stable release.

## License

No open-source license has been selected yet. Until a `LICENSE` file is added,
the code is visible for inspection but not granted for reuse under an
open-source license.
