---
name: kdh-providers-discuss
description: "Alias for providers-discuss. Use when the user asks for KDH provider discussion workflows with dynamic provider seats, rounds, auth preflight, input packs, gates, prompt deltas, and proof-gated Claude Team Agents workflows."
---

# kdh-providers-discuss

This is a compatibility alias for the public `providers-discuss` skill.

Use it exactly like `providers-discuss`:

- Start with the same intake gate: language, round count, seat count,
  provider/model/effort choices, agent profiles or default, topic,
  brainstorming mode, and input data path.
- Ask one question at a time. First ask for language in English, Korean,
  Chinese, Japanese, and Spanish, then continue in the selected language.
- Explain provider options with examples:
  Claude haiku/sonnet/opus-style models plus Team Agents, GPT/Codex
  gpt-5.5-style seats, Gemini, and manual import. Before naming exact models
  or efforts, refresh current model/effort options from official provider
  sources or local CLI discovery and show only about three common choices per
  selected provider. Mark exact model names and effort support as
  availability-dependent until auth/capability checks pass.
- After provider selection, run or instruct `providers-discuss auth-preflight`.
  If login is missing, show the provider login command and relay the official
  login URL when the provider CLI emits one. Do not capture tokens, cookies,
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
