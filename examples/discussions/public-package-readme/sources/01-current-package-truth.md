# Current Package Truth

This file summarizes the current package staging surface for provider seats.
It is derived from local files under:

`closed-door-training/workspaces/kdh-study/providers-discuss-public-package/package-staging/providers-discuss`

## Current Files Of Interest

- `README.md`: English public-facing package draft.
- `install.sh`: local command-link installer; no provider settings mutation.
- `bin/providers-discuss`: package CLI entrypoint.
- `providers_discuss/*.py`: package implementation modules.
- `examples/minimal-manual.config.json`: stable manual/import demo.
- `examples/codex-claude.config.json`: Codex/GPT plus Claude smoke-gated demo.
- `examples/claude-team-agents.config.json`: Claude Team Agents proof-gated demo.
- `examples/gemini-optional.config.json`: optional Gemini placeholder config.
- `examples/profile-balanced-kdh.config.json`: profile/default example.
- `examples/agents/kdh-mini-catalog.json`: prompt-only agent profile catalog.
- `skills/providers-discuss/SKILL.md`: package skill source.
- `tests/smoke-package.sh`: package smoke script.

## Existing README Positioning

The current README already says `providers-discuss` is:

- a file-backed local discussion runner
- a dynamic-round and dynamic-seat CLI
- a manual/import workflow
- a provider adapter shell for Codex, Claude, Claude Team Agents, Gemini, and
  manual seats
- a proof-gated Team Agents workflow
- a prompt-only agent profile catalog gate

The README already says it is not:

- a hidden provider automation daemon
- a vector database, memory system, or RAG server
- a token/cookie/OAuth collector
- a runner for BMAD, oh-my-agents, KDH agents, or third-party runtimes
- polished live dispatch for all providers

## Agent Profile Catalog Truth

The current mini catalog contains prompt-only role contracts:

- `kdh-ideation-catalyst`
- `kdh-research-synthesizer`
- `kdh-system-architect`
- `kdh-code-reviewer`
- `kdh-qa-verifier`
- `kdh-technical-writer`

Important boundary:

- Agent profiles shape prompts only.
- They do not grant tools, credentials, hooks, permissions, or filesystem
  access.
- `kdh-technical-writer` currently targets manual, Codex, and Claude Code, but
  not Claude Team Agents in the staging catalog.

## Recommended Public Honesty

The package should be presented as a trustworthy local orchestration substrate,
not as magical automatic provider control.

Best wording direction:

- "dynamic provider discussion runner"
- "file-backed artifacts and gates"
- "manual-first, proof-gated live adapters"
- "prompt-only agent profiles"
- "bring your own provider CLI/login"

Avoid wording direction:

- "fully automated multi-agent debate across all providers"
- "universal Team Agents automation"
- "OAuth auto-login"
- "agent catalog execution"
- "RAG/memory system"

## Open Decisions For Providers To Debate

- Should README lead with manual/import reliability or dynamic provider
  ambition?
- How much should it expose smoke-only maturity in the first viewport?
- Should package examples include a guided setup transcript?
- Should `configure` be the main beginner path, with JSON config as the
  advanced path?
- How should it explain Team Agents proof requirements without confusing users?
- How should it support future Gemini without overpromising current maturity?
- Should public docs include Korean and English READMEs from the start?
