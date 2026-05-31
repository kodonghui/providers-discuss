---
name: kdh-providers-discuss
description: "Use kdh-providers-discuss when a user wants to configure, run, inspect, or package a file-backed multi-provider discussion with dynamic rounds, provider seats, auth preflight, input packs, gates, prompt deltas, and Claude Team Agents workflows."
---

# kdh-providers-discuss

This is the canonical Codex skill for the `providers-discuss` CLI.

- Start with the same intake gate: language, round count, seat count,
  provider/model/effort choices, agent profiles or default, topic,
  brainstorming mode, and input data path.
- Ask one question at a time. First ask for language in English, Korean,
  Chinese, Japanese, and Spanish, then continue in the selected language.
- Immediately after language selection, show the remaining setup sequence as
  structured bullets: round count, seat count, provider type, model, reasoning
  effort, auth check, agent profile/default, topic, brainstorming, and input
  data path or input pack.
- At the round-count gate, explain that 1 to N rounds are possible. The default
  of 3 is not a limit.
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
  `- https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/model.md`
  `- local CLI: gemini /model, gemini --help, or gemini --model help when available`
- After provider selection, run or instruct `providers-discuss auth-preflight`.
  If login is missing, use a URL-first login gate: generate or surface the
  official provider CLI login URL and show that URL to the user. Do not invent,
  hardcode, scrape, or store unofficial URLs. Do not capture tokens, cookies,
  provider-home config bodies, browser state, credential files, or shell
  history.
- At the agent step, list available profiles with short descriptions and offer
  `default` using the balanced KDH preset.
- Ask explicitly whether the user wants no brainstorming, light brainstorming,
  or deep brainstorming before provider rounds.
- Prefer config-first runs with `providers-discuss validate-config`, then
  `providers-discuss init --config`.
- Run `providers-discuss auth-preflight` before live provider work.
- Start with `providers-discuss run-round --mode dry-run`.
- Use `providers-discuss run-round --mode manual-import` for the stable live
  workflow.
- Do not claim unsupported live adapters are mature.
- Do not add hooks, cron, daemons, provider-home mutation, browser OAuth
  automation, global wrappers, or token capture.

For the full operating contract, read `skills/providers-discuss/SKILL.md` in
this repository when available.
