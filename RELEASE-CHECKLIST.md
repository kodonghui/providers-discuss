# Release Checklist

Do not publish `kodonghui/providers-discuss` until every item is checked.

## Legal And Ownership

- [ ] License selected and committed.
- [ ] Copyright/ownership statement reviewed.

## Package Smoke

- [x] Copy this staged package to a temporary directory.
- [x] Run `bin/providers-discuss --help` from the temp copy.
- [x] Validate every file in `examples/*.config.json`.
- [x] Run the manual-only quick start from `README.md`.
- [x] Run `tests/smoke-package.sh` from the temp copy.

## Public Safety

- [x] README and examples do not require a private source checkout path.
- [x] README and examples do not include private usernames, OAuth tokens,
  cookies, credential files, browser state, shell history, or provider-home raw
  config.
- [x] `install.sh` only writes under the selected local user prefix.
- [x] No hook, cron, daemon, global wrapper, provider-home mutation, or browser
  OAuth automation is installed implicitly.

## Maturity Truth

- [x] Provider maturity table matches `adapter-capabilities`.
- [x] Manual import is the only stable live workflow advertised.
- [x] Codex exec-file is labeled structural.
- [x] Claude Code and Claude Team Agents are labeled smoke/proof-gated.
- [x] Gemini is labeled placeholder.
- [x] Unsupported live dispatch is documented honestly.

## Evidence

- [x] Fresh temp-package smoke path recorded in the release notes.
- [x] Full test suite passes in the source harness before publishing.
