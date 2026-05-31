# CEO Request And Boundary

This input file records the discussion objective and the current runtime
boundary for a future `providers-discuss` run. It is input data only. It is not
an execution log and it must not be treated as provider output.

## Current Phone-Side Boundary

- The CEO is currently on a phone.
- Do not run provider login or OAuth flows now.
- Do not mutate provider home directories, Claude settings, Codex settings,
  hooks, permissions, or workspace trust now.
- Prepare only the input material, draft config, and deterministic input pack.
- Live provider execution can start later from the desktop after the CEO
  explicitly confirms login/auth handling.

## Public Package Objective

Prepare a provider discussion for the future public repository:

- repository candidate: `kodonghui/providers-discuss`
- product: portable `providers-discuss` CLI and skill package
- goal: make the KDH provider-discussion method usable by other people outside
  this local KDH harness setup

The discussion should evaluate how to present, document, and package
`providers-discuss` so users can install it, choose seats/providers dynamically,
configure rounds, optionally use Claude Team Agents, optionally use Gemini,
and run manual/import workflows when provider login or live dispatch is not
available.

## CEO Feature Request, Normalized

The public package should eventually support:

- configurable seat count
- configurable provider list, including Codex/GPT, Claude, Claude Team Agents,
  Gemini, manual seats, and future provider adapters
- configurable model and reasoning/effort per seat
- configurable round count and round purpose
- an interactive setup flow that asks questions such as:
  - how many seats?
  - which providers and models?
  - what reasoning effort?
  - how many rounds?
  - what input folder or topic?
  - should Claude use Team Agents?
  - which roles or agent profiles should each seat/team use?
- source-folder packaging before discussion
- orchestrator review after each round
- prompt refinement from previous-round outputs
- claim-map and gate artifacts so unsupported claims do not silently become
  conclusions

## Runtime Maturity That Must Not Be Overstated

The README and package should be honest about current maturity:

- Manual/import workflow is the safest stable path.
- Dynamic config, source packaging, claim gates, and artifact verification are
  package-level strengths.
- Codex/GPT file-output dispatch exists structurally, but public live dispatch
  still needs hardening.
- Claude Code and Claude Team Agents are proof/smoke gated, not general
  polished multiround automation.
- Gemini is optional or placeholder until implemented and verified.
- Team Agents summary-only output is not sufficient proof.
- The package must not claim hidden automation, OAuth collection, browser state
  access, provider-home scraping, or automatic use of third-party agent
  runtimes.

## Discussion Question

Given the current README and package surface, what should the public package
say and implement next so that a user can install it, configure dynamic
providers/seats/rounds/agents, prepare input material, and run a trustworthy
multi-provider discussion without confusing the current smoke-only/live
maturity boundaries?
