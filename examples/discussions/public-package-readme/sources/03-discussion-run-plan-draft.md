# Discussion Run Plan Draft

This is a draft input plan for the later live run. It must be confirmed by the
CEO before execution.

## Draft Run Shape

- round count: 3
- seat count: 3
- seat A: Claude Team Agents, required
- seat B: Claude Team Agents, required
- seat C: GPT/Codex file-output seat, required
- live provider execution: deferred until desktop login/auth confirmation
- input packaging: prepared now

## Draft Rounds

### R1 - Product Positioning And Public User Flow

Each seat independently reads the package README/current-truth inputs and
proposes:

- who the public package is for
- what the README should promise
- what the README must not overpromise
- what beginner flow should be documented first
- what dynamic provider/seat/round/agent configuration should look like

### R2 - Challenge Unsupported Claims And Maturity Boundaries

Each seat challenges R1:

- locate claims that sound too mature
- separate stable/manual workflows from proof-gated or placeholder workflows
- identify missing install, auth, workspace, permission, or Team Agents warnings
- decide how to explain agent profiles without implying runtime agent execution

### R3 - Decision Contract And Implementation Gate

Each seat produces a final recommendation:

- README structure
- Korean README structure
- setup/configure flow
- public release checklist changes
- minimum tests/smokes before public repo publication
- exact blockers that must remain documented

## Draft Seats

### Seat A - Claude Team Product/Architecture

- provider: Anthropic
- transport: `claude_k_team_agents`
- model draft: `sonnet`
- effort draft: `max`
- timeout: `2400`
- Team Agents roles:
  - Ideation Catalyst
  - Research Synthesizer
  - System Architect
- required direct teammate messages: `6`

### Seat B - Claude Team Verification/Release

- provider: Anthropic
- transport: `claude_k_team_agents`
- model draft: `sonnet`
- effort draft: `max`
- timeout: `2400`
- Team Agents roles:
  - Code Reviewer
  - QA Verifier
  - Research Synthesizer
- required direct teammate messages: `6`

### Seat C - GPT/Codex Public Package Reviewer

- provider: OpenAI
- transport: `codex_exec_file`
- model draft: `gpt-5.5`
- reasoning effort draft: `medium`
- timeout: `2400`
- execution contract:
  - workspace-write sandbox
  - answer file required
  - stdout fallback allowed
  - completion marker: `KDH_CODEX_DONE`

## Questions To Resolve At Desktop Gate

- Keep Claude model as Sonnet for cost/speed, or switch to Opus/max as the
  stronger default?
- Use host provider logins directly or an isolated container/podman test
  workspace?
- Should Gemini be disabled for this run or added as an optional manual seat?
- Should the live run only generate README recommendations, or also patch the
  package staging files after R3?
- Should Korean README be committed in package staging after the discussion, or
  remain an input draft until release review?
