---
name: providers-discuss
description: "Use providers-discuss when a user wants to configure, run, inspect, or package a file-backed multi-provider discussion with dynamic rounds, provider seats, manual import fallback, auth preflight, input packs, gates, prompt deltas, and Claude Team Agents workflows."
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
  input data path. Run the login/auth gate after providers are selected and
  before agent profile assignment.
- Ask one intake question at a time. After each answer, move to the next
  question. Include short examples because many users will not know provider
  transports, effort levels, or agent profile names.
- First ask for language. Show the same choice in five languages as structured
  bullets, then continue in the selected language:
  `English: Choose a language:`
  `- English`
  `- Korean`
  `- Chinese`
  `- Japanese`
  `- Spanish`
  `Korean: 언어를 선택해주세요:`
  `- 영어`
  `- 한국어`
  `- 중국어`
  `- 일본어`
  `- 스페인어`
- Immediately after the language choice, explain the remaining setup order as
  structured bullets:
  `providers-discuss setup will continue in this order:`
  `- round count`
  `- seat count`
  `- provider type for each seat`
  `- model for each provider`
  `- reasoning effort for each provider`
  `- provider login/auth check`
  `- agent profile or default for each seat`
  `- topic/objective`
  `- brainstorming mode`
  `- input data path or input pack`
- At the round-count gate, say that any positive round count from 1 to N is
  possible. The default of 3 is only a default, not a limit.
- Before explaining exact model names or effort labels, run a current
  model/effort refresh gate. First say exactly:
  `사용 가능한 model과 effort를 최신정보로 검색하겠습니다.`
  Then prefer official provider docs and local CLI discovery, label the refresh
  date/source, and show about three commonly used model choices and about three
  effort choices per selected provider. Do not dump every model. Do not
  recommend one.
- Explain provider options as examples, not guaranteed availability. The
  package must still use `auth-preflight` and adapter capability checks.
  Always present choices as structured bullets, not comma-separated inline
  lists:
  `[gpt/codex]`
  `- One OpenAI/Codex CLI seat.`
  `- Good for analysis, code review, implementation planning, and file-output answers.`
  `[claude]`
  `- One normal Claude Code seat.`
  `- Good for architecture review, long-context reasoning, and design critique.`
  `[claude team agents]`
  `- One Claude Code seat that uses Claude Team Agents internally.`
  `- Claude coordinates its own teammates, they discuss the topic, and the Claude lead returns one final conclusion.`
  `[gemini]`
  `- One Gemini CLI seat.`
  `- Good for another independent provider perspective once installed and logged in.`
  Do not mention manual import in provider/model/effort choice screens. Manual
  import is not a provider option; describe it only in separate fallback/import
  workflow docs or when the user explicitly asks for manual import.
  After refresh, use this output shape:
  `[gpt/codex]`
  `- model: <refreshed GPT/Codex model 1>`
  `- model: <refreshed GPT/Codex model 2>`
  `- model: <refreshed GPT/Codex model 3>`
  `- effort: <refreshed effort 1>`
  `- effort: <refreshed effort 2>`
  `- effort: <refreshed effort 3>`
  Repeat the same structured shape for `[claude]`, `[claude team agents]`, and
  `[gemini]`.
- After providers are selected, run or instruct `providers-discuss
  auth-preflight`. If a required provider is missing or not logged in, show the
  provider-specific login command and, when the provider CLI emits an official
  login URL, relay that URL. If the CLI only generates the URL interactively,
  tell the user which command to run. Never capture OAuth tokens, cookies,
  provider-home config bodies, browser state, credential file contents, or
  shell history.
- At the agent profile step, list available profiles with one-line
  descriptions and offer `default`. If the user selected one Claude seat and
  one GPT/Codex seat, say for example: "You selected 1 Claude seat and 1
  GPT/Codex seat. Choose an agent profile for each, or choose default."
  Default means the `balanced-kdh` preset for the selected provider seats and
  Team Agents roles.
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
- Use `run-round --mode manual-import` only as the manual fallback/import
  workflow. Required seats need explicit `--answer seat_id=/path/to/answer.md`
  files.
- Do not call unsupported live adapters as if they are finished. Codex exec-file
  is structural, Claude Code is smoke-only, and Claude Team Agents must be
  verified with proof artifacts before claiming real Team Agents evidence.
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
