---
name: kdh-providers-discuss
description: "Use kdh-providers-discuss when a user wants to configure, run, inspect, or package a file-backed multi-provider discussion with dynamic rounds, provider seats, auth preflight, input packs, gates, prompt deltas, and Claude Team Agents workflows."
---

# kdh-providers-discuss

This is the canonical Codex skill for the `providers-discuss` CLI.

- Start with the same intake gate: language, one run-shape gate, auth check,
  agent profiles or default, topic, brainstorming mode, and input data path.
  The run-shape gate combines round count, seat count, provider type, model,
  and reasoning effort per seat.
- Ask one question at a time. First ask for language in English, Korean,
  Chinese, Japanese, and Spanish, then continue in the selected language.
- Immediately after language selection, show the remaining setup sequence as
  structured bullets: run-shape gate, auth check, agent profile/default, topic,
  deliverable profile, brainstorming, and input data path or input pack.
- At the run-shape gate, explain that 1 to N rounds are possible. The default
  of 3 is not a limit. Collect round count, seat count, provider type, model,
  and reasoning effort in that same gate.
- Explain provider options with structured bullets, not comma-separated inline
  lists:
  `[gpt/codex]`
  `- One OpenAI/Codex CLI seat.`
  `[claude]`
  `- One normal Claude Code seat.`
  `[claude team agents]`
  `- One Claude Code seat that uses Claude Team Agents internally, so Claude's
  teammates discuss the topic and the Claude lead returns one final conclusion.`
  `[gemini]`
  `- One Gemini CLI seat.`
  Do not mention manual import in provider/model/effort choice screens. Manual
  import is not a provider option; describe it only as a separate fallback when
  the user asks for manual import.
- Before naming exact models or efforts, first say:
  `사용 가능한 model과 effort를 최신정보로 검색하겠습니다.`
  Then refresh current model/effort options from the exact official sources
  below or local CLI discovery. Do not rely on search-result snippets,
  remembered model names, or unofficial pages. Show only about three common
  choices per selected provider. Mark exact model names and effort support as
  availability-dependent until auth/capability checks pass. Do not recommend
  one. If the official source cannot be opened, say the refresh failed and ask
  the user to provide the model/effort manually instead of guessing.
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
- After provider selection, run or instruct `providers-discuss auth-preflight`.
  If login is missing, use a URL-first login gate: generate or surface the
  official provider CLI login URL and show that URL to the user. Do not invent,
  hardcode, scrape, or store unofficial URLs. Do not capture tokens, cookies,
  provider-home config bodies, browser state, credential files, or shell
  history.
- At the agent step, load profiles from the configured catalog and list the
  actual `loaded_profiles` count with short descriptions. Do not hand-type a
  small fallback subset. The bundled full KDH catalog is
  `examples/agents/kdh-profile-catalog.json` and contains 15 profiles. Use
  `providers-discuss agent-profiles --config <config> --markdown` when a config
  exists, or `providers-discuss agent-profiles --catalog <catalog> --markdown`
  when only a catalog path is known. Offer `default` using the balanced KDH
  preset.
- Ask explicitly whether the user wants no brainstorming, light brainstorming,
  or deep brainstorming before provider rounds.
- After the topic/objective, ask for a deliverable profile: `discussion_summary`,
  `development_contract`, `readme_or_docs`, `research_synthesis`,
  `decision_memo`, `implementation_plan`, or a custom profile. Explain that
  profile-backed terminal rounds must produce a `KDH_FINAL_ARTIFACT` block and
  that `finalize` refreshes `result.json` from actual final artifacts.
- Prefer config-first runs with `providers-discuss validate-config`, then
  `providers-discuss init --config`.
- Run `providers-discuss auth-preflight` before live provider work.
  For Gemini CLI seats, trust handling is runner-owned: `auth-preflight`,
  `smoke-gemini-headless`, and Gemini live dispatch set
  `GEMINI_CLI_TRUST_WORKSPACE=true` for the child Gemini process only and
  record that in reports/proofs. Do not ask the user to remember this env var
  unless they are bypassing the runner.
- Start with `providers-discuss run-round --mode dry-run`.
- Use `providers-discuss advance` to continue through every legal runner-owned
  step until the run finishes or reaches a real blocker.
- Use `providers-discuss run-round --mode manual-import` for the stable live
  workflow.
- Treat the selected run-shape gate as binding during execution. Smoke/live
  commands must use the configured seat model, reasoning effort, permission
  mode, and timeout unless the user explicitly requests an override and records
  the reason.
- Do not call provider CLIs directly to collect official run answers. Do not use
  `claude -p` for Claude Team Agents. Official collection must go through
  `providers-discuss run-round`, a named smoke command, proof report, or
  explicit manual import.
- Do not claim unsupported live adapters are mature.
- Do not add hooks, cron, daemons, provider-home mutation, browser OAuth
  automation, global wrappers, or token capture.

For the full operating contract, read `skills/providers-discuss/SKILL.md` in
this repository when available.
