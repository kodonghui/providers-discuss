---
name: providers-discuss
description: "Use providers-discuss when a user wants to configure, run, inspect, or package a file-backed multi-provider discussion with dynamic rounds, provider seats, manual import, auth preflight, input packs, gates, prompt deltas, and proof-gated Claude Team Agents workflows."
---

# providers-discuss

Use this skill for the public `providers-discuss` CLI. The tool is a local,
file-backed discussion runner. It records prompts, answers, status files,
proof files, gates, hashes, and orchestrator prompt deltas under a run root.

## Ground Rules

- Begin with the intake gate unless the user already supplied every required
  choice. Explain that a run needs these decisions, in this order:
  language, round count, seat count, provider/model/effort per seat, agent
  profile per selected provider or default, topic, brainstorming mode, and
  input data path.
- Ask one intake question at a time. After each answer, move to the next
  question. Include short examples because many users will not know provider
  transports, effort levels, or agent profile names.
- First ask for language. Show the same choice in five languages and then
  continue in the selected language:
  `English: Choose a language: English, Korean, Chinese, Japanese, Spanish.`
  `Korean: 언어를 선택해주세요: 영어, 한국어, 중국어, 일본어, 스페인어.`
  `Chinese: 请选择语言: 英语, 韩语, 中文, 日语, 西班牙语.`
  `Japanese: 言語を選んでください: 英語, 韓国語, 中国語, 日本語, スペイン語.`
  `Spanish: Elige un idioma: inglés, coreano, chino, japonés, español.`
- Explain provider options as examples, not guaranteed availability. The
  package must still use `auth-preflight` and adapter capability checks.
  Current option families:
  `claude`: haiku/sonnet/opus-style models when available; efforts
  `low`, `medium`, `high`, `xhigh`, `max`; optional Team Agents with its own
  teammate roles and effort settings.
  `gpt/codex`: `gpt-5.5`-style Codex seat when available; efforts
  `low`, `medium`, `high`, `xhigh`.
  `gemini`: optional/placeholder until verified; `gemini-latest`-style model.
  `manual`: human-captured answer import.
- At the agent profile step, list available profiles with one-line
  descriptions and offer `default`. If the user selected one Claude seat and
  one GPT/Codex seat, say for example: "You selected 1 Claude seat and 1
  GPT/Codex seat. Choose an agent profile for each, or choose default."
  Default means the `balanced-kdh` preset: Codex/System Architect,
  Claude/Code Reviewer, Gemini/Ideation Catalyst, Manual/Technical Writer, and
  Team Agents roles for Ideation Catalyst, Research Synthesizer, System
  Architect, and QA Verifier.
- Treat `brainstorming` as an explicit intake choice. Ask whether the user
  wants no brainstorming, light brainstorming, or deep brainstorming before
  provider rounds. If enabled, keep it as a visible stage in the config or
  run notes.
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
