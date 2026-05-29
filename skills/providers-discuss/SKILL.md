---
name: providers-discuss
description: "Use providers-discuss when a user wants to configure, run, inspect, or package a file-backed multi-provider discussion with dynamic rounds, provider seats, manual import, auth preflight, input packs, gates, prompt deltas, and proof-gated Claude Team Agents workflows."
---

# providers-discuss

Use this skill for the public `providers-discuss` CLI. The tool is a local,
file-backed discussion runner. It records prompts, answers, status files,
proof files, gates, hashes, and orchestrator prompt deltas under a run root.

## Ground Rules

- Prefer a config-first workflow: `providers-discuss validate-config`, then
  `providers-discuss init --config`.
- Use `configure` only when the user wants an interactive or answers-JSON setup
  flow.
- Run `auth-preflight` before live provider work. It reports readiness and login
  hints, but must not capture OAuth tokens, cookies, provider-home raw config,
  browser state, or shell history.
- Start with `run-round --mode dry-run` to produce prompt/status/proof preview
  artifacts.
- Use `agent-profiles` before profile-aware runs to list compatible prompt-only
  roles from explicit catalogs or a config. Normal reports must stay clean:
  show role behavior and compatibility, not source profile ids, local source
  repo paths, tokens, or provider-home files.
- Use `run-round --mode manual-import` for the stable live workflow. Required
  seats need explicit `--answer seat_id=/path/to/answer.md` files.
- Do not call unsupported live adapters as if they are finished. Codex exec-file
  is structural, Claude Code is smoke-only, Claude Team Agents is smoke/proof
  gated, and Gemini is a placeholder until the package says otherwise.
- Do not add hooks, cron, daemons, provider-home mutation, hidden browser OAuth
  automation, global wrappers, or token capture.

## Common Flow

```bash
providers-discuss validate-config examples/minimal-manual.config.json
providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json --seat human_reviewer
providers-discuss init --config examples/minimal-manual.config.json --root ./.runs --run-id demo
providers-discuss preflight demo --root ./.runs
providers-discuss run-round demo --root ./.runs --round R1 --mode dry-run
providers-discuss run-round demo --root ./.runs --round R1 --mode manual-import --answer human_reviewer=answer.md
providers-discuss gate demo --root ./.runs --round R1
providers-discuss orchestrate demo --root ./.runs --after-round R1
providers-discuss verify demo --root ./.runs
```

`gate` requires a claim map at `claims/round-Rn-claim-map.json`. Provider
agreement is not truth; gate and claim support decide what can proceed.

## Team Agents

Use prompt-only first:

```bash
providers-discuss team-agents-prompt demo --root ./.runs --round R1 --seat claude_team --json
```

Use proof-report to inspect Team Agents evidence:

```bash
providers-discuss team-agents-proof-report demo --root ./.runs --proof logs/round-R1/claude_team.proof.json --json
```

Summary-only delegation, ordinary subagents, missing TeamCreate, missing
team-scoped Agent calls, missing direct teammate messages, or missing durable
artifacts must not pass as real Team Agents evidence.

Hook-assisted operation is explicit:

```bash
providers-discuss hook-config --run-id demo --root ./.runs --json
providers-discuss hook-config --run-id demo --root ./.runs --repair --json
providers-discuss hook-config --run-id demo --root ./.runs --remove --json
providers-discuss runtime-preflight --workspace "$PWD" --root ./.runs --run-id demo --trigger-mode prompt_only --json
```

`prompt_only` does not require hook configuration. Hook-assisted modes must fail
closed until the user explicitly installs hooks.

## Reporting

When reporting results, include exact run paths, command outcomes, verifier
status, blockers, and the next action. Do not claim live-provider readiness from
dry-run previews, local smoke fixtures, or fake proof artifacts.
