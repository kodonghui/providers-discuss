# providers-discuss

`providers-discuss` is a local, file-backed discussion runner for comparing AI
provider seats across multiple rounds. It records prompts, answers, logs,
status files, proof files, gates, hashes, source indexes, claim maps, and
orchestrator deltas under a run directory so a result can be inspected without
trusting chat scrollback.

Why now: this package prepares for the June 15 Claude `-p` policy and credit
change. Official provider answers must be collected through runner-owned
commands and auditable artifacts, not by ad hoc direct CLI calls.

## What It Is

- A local CLI for configuring multi-round, multi-seat provider discussions.
- A runner that writes observable artifacts under a run-state directory.
- A live dispatch surface for supported Codex, Claude Team Agents, and Gemini
  transports.
- A manual import fallback for already-captured answer files.
- A read-only agent profile catalog for assigning prompt-only roles to provider
  seats or Claude Team Agents teammates.
- A gate and verification workflow for claim maps, provider proofs, hashes, and
  final results.

## What It Is Not

- It is not a hidden provider automation daemon, cron job, memory system, vector
  database, or RAG server.
- It does not collect OAuth tokens, cookies, browser state, shell history, or
  provider-home raw config.
- It does not execute BMAD, oh-my-agents, KDH agent framework scripts, or any
  third-party agent runtime from a catalog.
- It does not treat direct `claude -p`, direct `codex`, or direct `gemini`
  output as an official provider answer.
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
- `$HOME/.codex/skills/kdh-providers-discuss`

It does not touch provider homes, OAuth files, Claude hooks, browser settings,
cron, daemons, or global system directories.

Optional shorter public skill alias:

```bash
./install.sh --with-public-alias
```

Uninstall:

```bash
./install.sh --uninstall
```

You can also run without installing:

```bash
bin/providers-discuss --help
```

## First Run Setup

A user-facing setup flow should happen in this order:

1. Choose language.
2. Choose the run shape in one binding gate:
   - round count
   - seat count
   - provider per seat
   - model per seat
   - reasoning effort per seat
   - whether a Claude seat uses Team Agents
3. Run provider login/auth preflight.
4. Choose an agent profile for each seat, or use `default`.
5. Write the topic/objective.
6. Choose a deliverable profile, such as `development_contract`,
   `readme_or_docs`, `research_synthesis`, `decision_memo`,
   `implementation_plan`, or a custom profile.
7. Choose brainstorming mode: `none`, `light`, or `deep`.
8. Provide input data paths or an existing input pack.

Round count can be any positive integer from 1 to N. The default is 3, but it
is not a limit.

Provider choices:

- `gpt/codex`: one OpenAI/Codex CLI seat.
- `claude`: one normal Claude Code seat.
- `claude team agents`: one Claude Code seat that uses Claude Team Agents
  internally and returns one lead conclusion.
- `gemini`: one Gemini CLI seat.

Manual import is not a provider choice. It is a fallback/import path when live
dispatch is unavailable or not desired.

Before showing exact model and effort choices, refresh current options:

```text
사용 가능한 model과 effort를 최신정보로 검색하겠습니다.
```

Exact model names and effort support are availability-dependent until local CLI
and auth checks pass. For Gemini, prefer:

```bash
bin/providers-discuss model-refresh --provider gemini --json
```

## Quick Start: 3-Round, 3-Seat Live Dispatch

Create a config with three rounds and three seats, then run:

```bash
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

bin/providers-discuss validate-config "$CONFIG"
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"

bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch

bin/providers-discuss status "$RUN_ID" --root "$ROOT"
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

`advance --round-mode live-dispatch` moves through every legal runner-owned
step until the selected round count is finished or a real blocker appears. For
a 3-round config, the runner dispatches R1, gates R1, writes the R2 prompt
delta, dispatches R2, gates R2, writes the R3 prompt delta, dispatches R3,
gates R3 as terminal, writes `result.json`, and finalizes.

If the config uses a deliverable profile, late-round prompts converge toward
that profile. A final provider answer can emit a runner-owned artifact block:

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...
<!-- /KDH_FINAL_ARTIFACT -->
```

The terminal gate extracts the block into the run root, checks required
sections, and records a deliverable gate. `finalize` refreshes `result.json`
from current final artifacts so stale metadata does not survive a final file
patch.

## Input Packs And Run-State Paths

Input packs belong in run state, not in the git repository.

When attached to a run, `build-input-pack` writes:

- `$ROOT/$RUN_ID/inputs/input-pack.md`
- `$ROOT/$RUN_ID/inputs/source-manifest.json`
- `$ROOT/$RUN_ID/config/source-index.json`

Provider prompts list these paths under "Run Context Files". Later rounds also
list prior answer, gate, orchestrator, and prompt-delta artifacts so providers
can read the prior round context.

The builder records paths, hashes, headings, bounded excerpts, and omission
reasons. It is not RAG, embeddings, GraphRAG, Obsidian, wiki generation, web
research, or LLM summarization.

## Provider And Adapter Status

Use `adapter-capabilities` to inspect the selected run or config:

```bash
bin/providers-discuss adapter-capabilities --config providers-discuss.config.json --json
bin/providers-discuss adapter-capabilities "$RUN_ID" --root "$ROOT" --json
```

Current adapter truth:

| User choice | Transport | Adapter | Current maturity | Live dispatch |
|---|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | `codex_exec_file` | `live_headless` | `run-round --mode live-dispatch` |
| `claude` | `claude_k` | `claude_code` | `smoke_only` | named `smoke-claude-k`; not normal multiround live dispatch |
| `claude team agents` | `claude_k_team_agents` | `claude_team_agents` | `live_team_agents` | `run-round --mode live-dispatch` or named smoke |
| `gemini` | `gemini_cli` | `gemini_cli` | `live_headless` | `run-round --mode live-dispatch` or named smoke |
| fallback | `manual` | `manual_import` | `fallback` | `run-round --mode manual-import` |

Codex live dispatch uses `codex exec` with a runner-owned output file and
completion marker. It must be allowed to write inside the run root.

Gemini live dispatch sets `GEMINI_CLI_TRUST_WORKSPACE=true` only for the child
Gemini process because Gemini CLI headless mode may reject an untrusted
directory before reaching auth. Reports and proofs record that child-process
workspace trust was applied. The runner does not mutate Gemini provider-home
config or copy credentials.

Claude Team Agents live dispatch asks Claude Code to use `TeamCreate`,
`TaskCreate`, team-scoped `Agent` calls, and `SendMessage`. Proof verification
fails summary-only delegation or ordinary subagent delegation without durable
Team Agents evidence.

## Agent Profiles

Agent profiles are prompt-only role contracts. They can shape a provider seat
or a Claude Team Agents teammate, but they do not grant tools, credentials,
hooks, filesystem permissions, or provider-home access.

List profiles before choosing them:

```bash
bin/providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json
bin/providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json --seat human_reviewer --markdown
bin/providers-discuss agent-profiles --catalog examples/agents/kdh-profile-catalog.json --transport gemini_cli
```

The bundled `examples/agents/kdh-profile-catalog.json` contains 15 profiles:

| Profile | Use |
|---|---|
| Code Reviewer | bug/risk review, quality critique, maintainability checks |
| Data Analyst | metrics, datasets, dashboards, structured data interpretation |
| Ideation Catalyst | divergent ideas, reframing, option expansion |
| Implementation Engineer | scoped code changes and practical implementation plans |
| Knowledge Curator | memory, wiki, context packs, provenance |
| Orchestrator Planner | large-goal decomposition and provider role coordination |
| Product Strategist | product/business framing and packaging |
| QA Verifier | test strategy, proof gates, verification design |
| Release Manager | release gates, CI/CD, package rollout |
| Research Synthesizer | evidence gathering and source comparison |
| Security Reviewer | credential safety, threat modeling, permission boundaries |
| System Architect | architecture tradeoffs and module boundaries |
| Technical Writer | README text, handoffs, user-facing explanations |
| UX Design Reviewer | workflow critique and interface wording |
| Web Research Operator | web/browser/data acquisition plans |

Reports show clean user-facing fields such as id, name, description, provider
targets, Team Agents fit, source profile count, catalog reference, and
compatibility. They do not dump source profile ids or local source repository
paths.

## Auth/Login Gate

`auth-preflight` checks selected enabled seats before live work:

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir auth-report
```

The report is sanitized. It records readiness classes such as
`installed_logged_in`, `installed_not_logged_in`, `missing_cli`, and
`manual_or_skipped`, plus a next action. It must not copy OAuth tokens, cookies,
provider-home config bodies, credential files, or shell history.

If a selected provider is not logged in, use a URL-first login gate:

- Codex/GPT: run `codex login --device-auth`, show the official URL it emits,
  then rerun `auth-preflight`.
- Claude: run `claude auth login`, show the official URL it emits, then rerun
  `auth-preflight`.
- Gemini: run `gemini`, complete `/auth` if prompted, show the official URL it
  emits, then rerun `auth-preflight`.

Do not invent, hardcode, scrape, or store unofficial login URLs. Treat login
URLs as transient login material.

## Manual Import Fallback

Manual import proves the artifact contract without live provider credentials.

```bash
work="$(mktemp -d)"
cp examples/minimal-manual.config.json "$work/providers-discuss.config.json"

run_id="$(bin/providers-discuss init \
  --config "$work/providers-discuss.config.json" \
  --root "$work/runs" \
  --run-id manual-demo | tail -n 1)"

bin/providers-discuss preflight "$run_id" --root "$work/runs"
bin/providers-discuss run-round "$run_id" --root "$work/runs" --round R1 --mode dry-run

printf '# Manual answer\n\nManual evidence is preserved.\n' > "$work/manual-answer.md"

bin/providers-discuss run-round "$run_id" \
  --root "$work/runs" \
  --round R1 \
  --mode manual-import \
  --answer "human_reviewer=$work/manual-answer.md"
```

Manual import still writes answer, status, proof, event, hash, and manifest
artifacts. It is a fallback path, not a substitute for live adapter proof when
live provider execution is the goal.

## Inspecting A Run

Important run artifacts:

- `run.json`
- `events.jsonl`
- `config/provider-seats.json`
- `config/source-index.json`
- `inputs/input-pack.md`
- `prompts/round-Rn/*.prompt.md`
- `answers/round-Rn/*.md`
- `logs/round-Rn/*.status.json`
- `logs/round-Rn/*.proof.json`
- `claims/round-Rn-claim-map.json`
- `gates/round-Rn-gate.md`
- `orchestrator/round-Rn-review.md`
- `final/*`
- `result.json`
- `verify.json`

Useful commands:

```bash
bin/providers-discuss status "$RUN_ID" --root "$ROOT" --json
bin/providers-discuss verify "$RUN_ID" --root "$ROOT" --json
bin/providers-discuss verify-proof "$RUN_ID" --root "$ROOT" --kind transport --proof logs/round-R1/gpt_readme.proof.json
bin/providers-discuss verify-proof "$RUN_ID" --root "$ROOT" --kind team-agents --proof logs/round-R1/claude_team_readme.proof.json
```

## Troubleshooting

- `validate-config` fails: check `schema`, duplicate seat ids,
  provider/transport pairing, reasoning effort, Codex writable sandbox, and
  Team Agents role count.
- `auth-preflight` blocks: required provider credentials are not ready. Log in
  with the provider's official CLI or mark that seat optional/disabled.
- Gemini reports an untrusted directory: use the runner path; it sets
  `GEMINI_CLI_TRUST_WORKSPACE=true` for the child process and records that in
  reports/proofs.
- A live round stops early: inspect `raw-output-manifest.md`,
  `logs/round-Rn/*.status.json`, and `verify.json`.
- `gate` returns `return_to_round`: add or fix the claim map, provider answer,
  support evidence, or deliverable profile sections.
- `verify` fails: inspect `verify.json`; the blocker names the missing artifact
  or failed provider status.

## Release Status

This repository is public early-stage work. Before publishing a stable release,
run the verification commands in `AGENTS.md` and resolve the license blocker
below.

## License

No open-source license has been selected yet. Until a `LICENSE` file is added,
the code is visible for inspection but not granted for reuse under an
open-source license.
