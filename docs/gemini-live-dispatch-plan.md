# Gemini Live Dispatch Plan

Status: implementation path added. Do not claim a target machine is Gemini live
ready until its local `auth-preflight`, `smoke-gemini-headless`, and normal
`run-round --mode live-dispatch` gates pass with real artifacts.

## Objective

Make `gemini_cli` a usable provider seat in `providers-discuss` by adding a
headless Gemini CLI smoke path, authentication probe, and live answer artifact
capture path.

## Current Evidence

- `gemini_cli` already exists in the public package config surface as
  `provider=google`, `transport=gemini_cli`.
- `examples/gemini-optional.config.json` keeps Gemini as a disabled optional
  future seat.
- `providers_discuss/provider_adapters.py` marks `gemini_cli` as
  `maturity=placeholder`, `live_dispatch_available=False`, and
  `live_dispatch=not_implemented_in_p6`.
- `providers_discuss/provider_auth.py` looks for a `gemini` executable but has
  no real login-status probe yet.
- In the current Podman lab, enabling Gemini as a required seat produces
  `missing_cli`, which is the correct blocker until the CLI is installed.

## Official Research Snapshot

Sources checked on 2026-05-30:

- Gemini CLI README:
  `https://github.com/google-gemini/gemini-cli/blob/main/README.md`
- Gemini CLI headless docs:
  `https://google-gemini.github.io/gemini-cli/docs/cli/headless.html`
- Gemini CLI authentication docs:
  `https://google-gemini.github.io/gemini-cli/docs/get-started/authentication.html`
- Gemini CLI commands docs:
  `https://google-gemini.github.io/gemini-cli/docs/cli/commands.html`

Conclusions:

- Install options include `npx @google/gemini-cli`, global npm install
  `npm install -g @google/gemini-cli`, Homebrew, MacPorts, and conda-based
  Node environments.
- Headless mode uses `gemini -p "query"` or `gemini --prompt "query"`.
- Headless output can be plain text, JSON, or stream JSON with
  `--output-format`.
- Model selection uses `-m/--model`.
- Useful headless options include `--include-directories`, `--all-files`,
  `--debug`, `--approval-mode`, and `--yolo`.
- For headless authentication, Gemini CLI can use an existing cached login. If
  there is no cached credential, it needs environment-based auth such as
  `GEMINI_API_KEY`, Vertex `GOOGLE_GENAI_USE_VERTEXAI=true` plus
  `GOOGLE_API_KEY`, or Vertex ADC/service-account variables.
- Google-account login opens a browser flow and caches credentials locally for
  later sessions. It requires a browser that can reach the CLI's localhost
  callback.
- The `/auth` command exists inside the interactive CLI, but there is no
  documented standalone `gemini auth status` command equivalent to
  `codex login status` or `claude auth status --json`.

## Accepted Approach

Use Gemini CLI as a headless subprocess provider:

```bash
cat <prompt-path> | gemini \
  --prompt "Execute the provider-discuss prompt from stdin. Return only the final answer." \
  --output-format json \
  --model <configured-model>
```

The adapter should write:

- `answers/round-Rn/<seat_id>.md`
- `logs/round-Rn/<seat_id>.raw.json` or `.stdout.log`
- `logs/round-Rn/<seat_id>.stderr.log`
- `logs/round-Rn/<seat_id>.status.json`
- `logs/round-Rn/<seat_id>.proof.json`

If JSON output parses, extract the main response. If JSON parsing fails, capture
stdout as raw fallback and mark the status as degraded rather than silently
passing.

## Rejected / Deferred Approaches

- Do not use `--yolo` by default. `providers-discuss` only needs an answer
  artifact, not autonomous file edits or shell execution.
- Do not scrape `~/.gemini` or copy cached credentials into reports.
- Do not assume OAuth login can be completed non-interactively. Use a human
  login gate or environment variables.
- Do not mark normal multiround Gemini live dispatch as complete after only
  `gemini --version` or a dry run.
- Do not hardcode exact latest model names in the package. Keep the
  model/effort refresh gate.

## Implementation Plan

### M01 - Install and Discovery Gate

Add docs and helper checks for installing Gemini CLI:

```bash
npm install -g @google/gemini-cli@latest
gemini --version
gemini --help
```

Acceptance:

- `auth-preflight` reports `missing_cli` when absent.
- `auth-preflight` reports a sanitized installed state when `gemini` exists.
- No credential files are read or logged.

### M02 - Authentication Gate

Implement Gemini auth readiness as a real bounded probe, because the CLI has no
documented standalone `auth status` command.

Probe order:

1. If no `gemini` executable: `missing_cli`.
2. If safe environment auth is present (`GEMINI_API_KEY`, or Vertex variables):
   run a tiny headless probe.
3. If no env auth but cached login may exist: run the same tiny headless probe.
4. If the probe exits with login/auth text, classify as
   `installed_not_logged_in`.
5. If the probe succeeds and returns expected text, classify as
   `installed_logged_in`.

Probe command shape:

```bash
gemini -p "Reply with exactly: GEMINI_AUTH_OK" --output-format json --model <model>
```

Acceptance:

- The probe is timeout-bounded.
- It stores stdout/stderr only in sanitized proof logs.
- It does not record API keys, OAuth files, cookies, browser state, or shell
  history.
- If login is missing, report how to proceed:
  `gemini` interactive `/auth`, `GEMINI_API_KEY`, or Vertex credentials.

### M03 - Headless Smoke Command

Add a named smoke command before normal live dispatch, for example:

```bash
providers-discuss smoke-gemini-headless <run-id> \
  --root <run-root> \
  --round R1 \
  --seat gemini_optional \
  --gemini-bin "$(command -v gemini)" \
  --timeout-seconds 2400
```

The smoke should create a minimal run prompt and require a deterministic marker:

```text
Return a short Markdown answer ending with KDH_GEMINI_DONE.
```

Acceptance:

- `answers/round-R1/<seat>.md` exists and contains `KDH_GEMINI_DONE`.
- Status JSON records command, exit code, timeout, model, output format, and
  failure class.
- Proof JSON is accepted by `verify-proof --kind transport` or a new
  `--kind gemini-headless` verifier.

### M04 - Provider Adapter Live Dispatch

After smoke passes, wire `gemini_cli` into provider adapter execution.

Command shape:

```bash
cat "<prompt_path>" | gemini \
  --prompt "Execute the provider-discuss prompt from stdin. Write a complete provider answer." \
  --output-format json \
  --model "<model>"
```

Optional context:

- Use `--include-directories <dir1,dir2>` only for explicitly selected input
  folders.
- Prefer already-built input packs over broad `--all-files`.

Acceptance:

- `adapter-capabilities` changes Gemini from `placeholder` to the appropriate
  verified maturity only after smoke/live gates pass.
- Normal run artifacts are identical in shape to other provider seats.
- `manual-import` remains the fallback.

### M05 - Tests and Public Package Update

Add tests for:

- Missing CLI.
- Installed but not logged in.
- Headless probe success using a fake `gemini` executable.
- JSON response extraction.
- Raw stdout fallback.
- Timeout failure.
- Config with enabled required Gemini seat.
- Package smoke includes Gemini helper surfaces.

Acceptance:

```bash
tests/smoke-package.sh
python3 -m unittest discover -s tests -v
```

For public package staging, run the package smoke and push both:

- `/home/opc/kdh-harness`
- `https://github.com/kodonghui/providers-discuss`

## Failure Gates

Stop and report, do not continue, if:

- Gemini CLI cannot be installed in the target environment.
- A required Gemini seat is not logged in.
- Headless `-p` hangs or times out.
- The response artifact is missing or does not contain the required marker.
- The only evidence is a dry run, command preview, or unsupported adapter path.

## CEO-Facing Status Rule

Use these labels:

- `Gemini selectable`: config/auth surface exists.
- `Gemini installed`: CLI found and version captured.
- `Gemini authenticated`: bounded headless probe passed.
- `Gemini smoke passed`: answer/status/proof artifacts passed verification.
- `Gemini live provider ready`: normal provider round produces accepted
  artifacts and adapter maturity is updated.

Anything below the final label is not full live-provider readiness.
