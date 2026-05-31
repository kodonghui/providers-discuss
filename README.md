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
- A provider adapter shell for Codex, Claude, Claude Team Agents, and Gemini.
- A manual import fallback for human-captured answers stored as files.
- A Claude Team Agents workflow where one Claude seat can use internal
  teammates to discuss the topic and return one lead conclusion; proof reports
  verify whether that evidence is real.
- A read-only agent profile catalog gate for assigning prompt-only roles to
  provider seats or Claude Team Agents teammates.

## What It Is Not

- It is not a hidden provider automation daemon.
- It is not a vector database, memory system, or RAG server.
- It does not collect OAuth tokens, cookies, browser state, shell history, or
  provider-home raw config.
- It does not execute BMAD, oh-my-agents, KDH agent framework scripts, or any
  third-party agent runtime from a catalog.
- It does not currently provide polished live dispatch for Codex or normal
  multiround Claude Team Agents.
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

It does not modify provider settings or install hooks. Restart Codex after
installing so the skill is loaded. `kdh-providers-discuss` is the canonical
skill name.

Optional shorter public alias:

```bash
./install.sh --with-public-alias
```

This also installs `$HOME/.codex/skills/providers-discuss`. Use it only when
you intentionally want both skill names to appear.

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

bin/providers-discuss advance "$run_id" --root "$work/runs" --round-mode dry-run || true
bin/providers-discuss status "$run_id" --root "$work/runs"
```

`advance` moves through every legal runner-owned step until the run finishes or
hits a real blocker such as missing provider answers, missing claim map,
unsupported live dispatch, or missing `result.json`. It does not invent
provider answers or claim maps. In this two-round manual example, it gates R1,
orchestrates R2, writes R2 prompts, and then stops at `provider_answers_needed`.

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
- `examples/gemini-live.config.json`
- `examples/profile-balanced-kdh.config.json`

For user-facing setup, follow the staged intake workflow in
`docs/intake-workflow.md`: language, run shape, auth, agent profiles, topic,
brainstorming mode, and input data path. Present every option set as structured
sections and bullets, not inline comma-separated lists.
Immediately after language selection, explain the remaining setup order:
run-shape gate, auth check, agent profile/default, topic, brainstorming, and
input data path or input pack. The run-shape gate combines round count, seat
count, provider type, model, and reasoning effort per seat. It must say that
any positive round count from 1 to N is allowed; the default of 3 is not a
limit.

Before asking the user to choose exact provider models or reasoning efforts,
say `사용 가능한 model과 effort를 최신정보로 검색하겠습니다.`, then refresh
the current model/effort options from the exact official provider sources or
local CLI discovery. Do not rely on search-result snippets, remembered model
names, or unofficial pages. Show refreshed options under provider headings such
as `[gpt/codex]`, `[claude]`, `[claude team agents]`, and `[gemini]`. Do not
recommend one; just show the available choices and then run `auth-preflight`
for the selected seats. If the official source cannot be opened, say the
refresh failed and ask the user to provide the model/effort manually instead of
guessing. Do not show manual import in the provider/model/effort choice
screens; keep it only as a separate fallback/import workflow.

Official/current model sources:

- `[gpt/codex]`
  - `https://platform.openai.com/docs/models`
  - local CLI: `codex debug models`, `codex /model`, or `codex --help`
- `[claude]`
  - `https://platform.claude.com/docs/en/about-claude/models/overview`
  - `https://platform.claude.com/docs/en/about-claude/models/model-ids`
  - local CLI: `claude --help` and Claude Code model picker
- `[claude team agents]`
  - `https://platform.claude.com/docs/en/about-claude/models/overview`
  - `https://platform.claude.com/docs/en/about-claude/models/model-ids`
  - local CLI: `claude --help` and Claude Code model picker
- `[gemini]`
  - `https://ai.google.dev/gemini-api/docs/models`
  - `https://ai.google.dev/api/models`
  - local dynamic refresh: `providers-discuss model-refresh --provider gemini --json`
  - `https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/model.md`
  - local CLI: `gemini /model`, `gemini --help`, or `gemini --model help` when available

For Gemini, prefer the dynamic refresh command or parse the opened official
model page/API reference directly. List the newest stable Flash model discovered
from the official source before older Flash/Pro options. Do not hardcode a
specific Gemini version; official model pages can change faster than this
package.

## Agent Profiles

Agent profiles are prompt-only role contracts. They can shape a provider seat
or a Claude Team Agents teammate, but they do not grant tools, credentials,
hooks, filesystem permissions, or provider-home access.

List profiles before choosing them:

```bash
bin/providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json
bin/providers-discuss agent-profiles --config examples/profile-balanced-kdh.config.json --seat human_reviewer --markdown
bin/providers-discuss agent-profiles --catalog examples/agents/kdh-profile-catalog.json --transport manual
```

The bundled `examples/agents/kdh-profile-catalog.json` contains the full
15-profile KDH prompt-role catalog. `examples/agents/kdh-mini-catalog.json` is
kept only as a small fixture. Use `agent_profile_id` per seat or enable
`agent_profile_defaults` with `balanced-kdh`. Normal reports show clean
user-facing fields such as id, name, description, provider targets, Team Agents
fit, source profile count, catalog reference, and compatibility. They do not
dump source profile ids or local source repository paths.

## Auth/Login Gate

`auth-preflight` checks selected enabled seats before live work:

```bash
bin/providers-discuss auth-preflight examples/codex-claude.config.json --report-dir auth-report
```

The report is sanitized. It records readiness classes such as
`installed_logged_in`, `installed_not_logged_in`, `missing_cli`, and
`manual_or_skipped`, plus a next action. It must not copy OAuth tokens, cookies,
provider-home config bodies, or shell history.

If a selected provider is not logged in, use a URL-first login gate. Generate
or surface the official provider CLI login URL and show that URL to the user.
Do not invent, hardcode, scrape, or store unofficial URLs. Treat login URLs as
transient login material; do not copy OAuth tokens, cookies, browser state,
provider-home config bodies, credential file contents, or shell history into
artifacts.

URL-first examples:

- Codex/GPT:
  - run `codex login --device-auth`
  - show the official URL it emits
  - rerun `auth-preflight` after completion
- Claude:
  - run `claude auth login`
  - show the official URL it emits
  - rerun `auth-preflight` after completion
- Gemini:
  - run `gemini`
  - complete `/auth` if prompted
  - show the official URL it emits
  - rerun `auth-preflight` after completion

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
| manual_import | manual | fallback | manual-import only; not a provider selection |
| codex_exec_file | codex_exec_file | structural | not polished public live dispatch |
| claude_code | claude_k | smoke_only | smoke-claude-k only |
| claude_team_agents | claude_k_team_agents | smoke_only | smoke-claude-team-agents plus proof verifier |
| gemini_cli | gemini_cli | live_headless | smoke-gemini-headless or run-round live-dispatch |

Use `adapter-capabilities` to inspect the current truth:

```bash
bin/providers-discuss adapter-capabilities --config examples/claude-team-agents.config.json --json
```

Gemini headless path:

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir auth-report
bin/providers-discuss smoke-gemini-headless <run-id> --root <runs> --round R1 --seat gemini_required --gemini-bin "$(command -v gemini)" --json
bin/providers-discuss run-round <run-id> --root <runs> --round R1 --mode live-dispatch --cli-path "gemini_cli=$(command -v gemini)"
```

Gemini uses the official headless CLI shape `cat prompt.md | gemini --prompt
... --output-format json --model ...`. The runner sets
`GEMINI_CLI_TRUST_WORKSPACE=true` only for the child Gemini process because
Gemini CLI may reject an untrusted directory before reaching auth. Reports and
proofs record that child-process workspace trust was applied. The runner stores
stdout, stderr, parsed JSON, answer, status, and transport proof artifacts. It
never copies Gemini credential files or API keys into reports.

## Claude Team Agents

User-facing meaning: choose `claude team agents` when you want one Claude Code
seat to use Claude's internal Team Agents feature. Claude should coordinate its
own teammates, have them discuss the topic, and return one final lead
conclusion.

Implementation meaning: the package still verifies Team Agents evidence with
smoke/proof artifacts so summary-only delegation is not mistaken for real Team
Agents work.

Prompt-only path:

```bash
bin/providers-discuss team-agents-prompt <run-id> --root <runs> --round R1 --seat claude_team --json
```

This writes `prompts/round-R1/claude_team.team-agents-prompt.md`. It does not
launch Claude and does not install hooks.

Proof-report path:

```bash
bin/providers-discuss team-agents-proof-report <run-id> --root <runs> --proof logs/round-R1/claude_team.team-agents-smoke.proof.json --json
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
