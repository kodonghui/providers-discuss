---
name: kdh-providers-discuss
description: "Alias for providers-discuss. Use when the user asks for KDH provider discussion workflows with dynamic provider seats, rounds, auth preflight, input packs, gates, prompt deltas, and proof-gated Claude Team Agents workflows."
---

# kdh-providers-discuss

This is a compatibility alias for the public `providers-discuss` skill.

Use it exactly like `providers-discuss`:

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
