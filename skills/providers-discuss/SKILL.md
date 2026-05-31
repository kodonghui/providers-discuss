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
  language, one run-shape gate, auth check, agent profile per selected provider
  or default, topic, brainstorming mode, and input data path. The run-shape gate
  combines round count, seat count, provider type, model, and reasoning effort
  per seat. Run the login/auth gate after providers are selected and before
  agent profile assignment.
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
  `- run shape gate: round count, seat count, provider/model/effort per seat`
  `- provider login/auth check`
  `- agent profile or default for each seat`
  `- topic/objective`
  `- brainstorming mode`
  `- input data path or input pack`
- At the run-shape gate, say that any positive round count from 1 to N is
  possible. The default of 3 is only a default, not a limit. Collect seat count,
  provider type, model, and reasoning effort in the same gate instead of
  splitting them into separate conceptual gates.
- Before explaining exact model names or effort labels, run a current
  model/effort refresh gate. First say exactly:
  `사용 가능한 model과 effort를 최신정보로 검색하겠습니다.`
  Then open the exact official sources below or use local CLI discovery; do not
  rely on search-result snippets, remembered model names, or unofficial blog
  posts. Label the refresh date/source, and show about three commonly used
  model choices and about three effort choices per selected provider. Do not
  dump every model. Do not recommend one. If the official source cannot be
  opened, say the refresh failed and ask the user to provide the model/effort
  manually instead of guessing.
  Official/current sources:
  `[gpt/codex]`
  `- https://platform.openai.com/docs/models`
  `- local CLI: codex debug models, codex /model, or codex --help`
  `[claude]`
  `- https://platform.claude.com/docs/en/about-claude/models/overview`
  `- https://platform.claude.com/docs/en/about-claude/models/model-ids`
  `- local CLI: claude --help and Claude Code model picker`
  `[claude team agents]`
  `- https://platform.claude.com/docs/en/about-claude/models/overview`
  `- https://platform.claude.com/docs/en/about-claude/models/model-ids`
  `- local CLI: claude --help and Claude Code model picker`
  `[gemini]`
  `- https://ai.google.dev/gemini-api/docs/models`
  `- https://ai.google.dev/api/models`
  `- local dynamic refresh: providers-discuss model-refresh --provider gemini --json`
  `- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/model.md`
  `- local CLI: gemini /model, gemini --help, or gemini --model help when available`
  Gemini-specific freshness rule: prefer the dynamic refresh command or parse
  the opened official model page/API reference directly. List the newest stable
  Flash model discovered from the official source before older Flash/Pro
  options. Do not hardcode a specific Gemini version; official model pages can
  change faster than this package.
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
  auth-preflight`. If a required provider is missing or not logged in, use a
  URL-first login gate: generate or surface the official provider CLI login URL
  and show that URL to the user. Do not invent, hardcode, scrape, or store
  unofficial URLs. If the CLI only generates the URL interactively, start or
  instruct that official flow. Never capture OAuth tokens, cookies,
  provider-home config bodies, browser state, credential file contents, or
  shell history.
- At the agent profile step, load profiles from the configured catalog and list
  the actual `loaded_profiles` count with one-line descriptions; do not
  hand-type a small fallback subset. The bundled full KDH catalog is
  `examples/agents/kdh-profile-catalog.json` and contains 15 profiles. Use
  `providers-discuss agent-profiles --config <config> --markdown` when a config
  exists, or `providers-discuss agent-profiles --catalog <catalog> --markdown`
  when only a catalog path is known. Offer `default`; it means the
  `balanced-kdh` preset for the selected provider seats and Team Agents roles.
  If the user selected one Claude seat and one GPT/Codex seat, say for example:
  "You selected 1 Claude seat and 1 GPT/Codex seat. Choose an agent profile for
  each, or choose default."
- Treat `brainstorming` as an explicit intake choice. Ask whether the user
  wants no brainstorming, light brainstorming, or deep brainstorming before
  provider rounds. If enabled, keep it as a visible stage in the config or
  run notes.
- Prefer a config-first workflow: `providers-discuss validate-config`, then
  `providers-discuss init --config`.
- Use `configure` only when the user wants an interactive or answers-JSON setup
  flow.
- Use `advance` as the default resume/continue command after init/preflight or
  after a gate. It should move through every legal runner-owned step until the
  run finishes or hits a real blocker such as missing provider answers, missing
  claim map, unsupported live dispatch, or missing `result.json`.
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
- Do not call provider CLIs directly to create official run answers. Do not run
  `claude -p`, `codex exec`, or `gemini` by hand and then describe that as
  runner live dispatch. Official run collection must go through
  `providers-discuss run-round`, a named smoke command, or explicit
  `manual-import` of already-created answer files. Providers must only produce
  answer content; status, proof, event, hash, gate, and orchestrator artifacts
  are runner-owned.
- Do not call unsupported live adapters as if they are finished. Codex exec-file
  is structural, Claude Code is smoke-only, and Claude Team Agents must be
  verified with proof artifacts before claiming real Team Agents evidence.
- Treat the selected run-shape gate as binding during execution. Smoke/live
  commands must use the configured seat model, reasoning effort, permission
  mode, and timeout unless the user explicitly requests an override and records
  the reason.
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
providers-discuss advance demo --root ./.runs --round-mode dry-run
providers-discuss verify demo --root ./.runs
```

`gate` requires a claim map at `claims/round-Rn-claim-map.json`. Provider
agreement is not truth; gate and claim support decide what can proceed.
`advance` does not invent provider answers or claim maps; it moves
automatically through the legal steps that already have their required inputs.

## Team Agents

Use prompt-only first:

```bash
providers-discuss team-agents-prompt demo --root ./.runs --round R1 --seat claude_team --json
```

Use proof-report to inspect Team Agents evidence:

```bash
providers-discuss team-agents-proof-report demo --root ./.runs --proof logs/round-R1/claude_team.team-agents-smoke.proof.json --json
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
