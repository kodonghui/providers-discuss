# providers-discuss Agent Rules

## Role

This repository owns the portable `providers-discuss` package: a local,
file-backed discussion runner for comparing multiple AI provider seats.

## Boundaries

- Keep the package local-first and observable.
- Do not add hidden daemons, cron jobs, background workers, browser automation,
  provider-home scraping, OAuth token collection, or implicit hooks.
- Do not claim mature live dispatch for adapters that are only structural,
  smoke-only, or placeholder.
- Agent profiles are prompt-only role contracts. They must not imply runtime
  agent execution, extra tools, credentials, or filesystem permissions.
- Provider outputs belong in run artifacts such as `answers/`, `logs/`,
  `claims/`, `gates/`, and `orchestrator/`; providers must not write the event
  bus directly.

## Current Maturity

- `manual_import`: stable manual/import workflow.
- `codex_exec_file`: structural file-output adapter; public live dispatch still
  needs hardening.
- `claude_k`: smoke-gated Claude Code transport.
- `claude_k_team_agents`: one Claude Code seat using internal Claude Team
  Agents; proof artifacts verify that real Team Agents behavior occurred.
- `gemini_cli`: live headless adapter after local auth-preflight passes.

## Development Rules

- Prefer Python standard library for the current package.
- Keep CLI behavior explicit and recoverable.
- At the start of a discussion intake, ask the user to choose the conversation
  language first. Supported intake languages are English, Korean, Chinese,
  Japanese, and Spanish; after the choice, continue in the selected language.
- Immediately after language selection, show the remaining setup order before
  asking for round count.
- Combine round count, seat count, provider type, model, and reasoning effort
  into one run-shape gate. The gate must say that 1 to N rounds are possible;
  the default of 3 is not a limit.
- Present intake choices as structured sections and bullets, not inline
  comma-separated option lists.
- Manual import is not a provider selection. Keep it as a fallback/import
  workflow for human-captured answer files, and do not mention it during
  provider/model/effort selection.
- Keep configs and examples free of private paths, OAuth tokens, cookies,
  provider-home config bodies, browser state, and shell history.
- Login gates are URL-first: surface official provider CLI login URLs when
  possible, but do not invent, hardcode, scrape, or persist unofficial URLs.
- Model/effort gates must use exact official provider source URLs or local CLI
  discovery. Do not rely on search-result snippets, remembered model names, or
  unofficial pages, and do not guess exact version numbers when refresh fails.
- Update README maturity claims together with adapter capability changes.
- If a change touches provider execution, add or update a smoke/proof path.
- Skills and agents must not call provider CLIs directly to collect official
  run answers. Use `bin/providers-discuss run-round`, named smoke commands,
  `team-agents-proof-report`, `advance`, or explicit `manual-import` of
  already-created answer files. Do not use `claude -p` for Claude Team Agents,
  and do not let providers write runner-owned status, proof, event, hash, gate,
  or orchestrator artifacts.

## Verification

Before publishing or handing off changes:

```bash
bin/providers-discuss --help
for config in examples/*.config.json; do
  bin/providers-discuss validate-config "$config" --json >/dev/null
done
tests/smoke-package.sh
```

For docs-only changes, run:

```bash
git diff --check
```
