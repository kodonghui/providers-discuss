# providers-discuss Input Pack

This pack is a deterministic convenience projection. Raw source files plus SHA-256 hashes are authoritative.

## Objective

Write the public providers-discuss README.md. Cover installation, input folder preparation, provider/seat/round/agent configuration, manual/import execution, and current live-dispatch maturity boundaries clearly.

## Source Directories

- `examples/discussions/public-package-readme/sources`

## Source Table

| source_id | path | size_bytes | sha256 |
|---|---|---:|---|
| `SRC-0001` | `00-ceo-request-and-boundary.md` | 3275 | `4d71979b9f6ffcb484dd3e568455c437997f47c278bbff35dbe6f81677cdcc2e` |
| `SRC-0002` | `01-current-package-truth.md` | 3389 | `89b43866009038414209403f1c04d5c3e5936a5834c9acc7a267979245128e5b` |
| `SRC-0003` | `02-proposed-public-readme-ko-draft.md` | 3605 | `b6f5224449b0a90b7f099bd5afc6c867ecabdd74e2fb8589690639bbe9e125f1` |
| `SRC-0004` | `03-discussion-run-plan-draft.md` | 2924 | `8a2a3a41c274e3bcf3f5f4a689fa462d7b8b352eba4c746e8dcc3510a6fcb485` |
| `SRC-0005` | `04-terms-podman-docker-sandbox.md` | 1130 | `c7b71f82d2eade034ffd064b8bcbcd0869f4dbfabaea0c9402ce019edf2f7f7f` |
| `SRC-0006` | `README.en.current.md` | 8852 | `a75dc38216315c767be5a01afd0ed71cc4fe2eca3f01172106e08ae2a93c4a5e` |

## Source Excerpts

### SRC-0001 - 00-ceo-request-and-boundary.md

- kind: `text/markdown`
- line_count: `78`
- summary: 00-ceo-request-and-boundary.md; headings: CEO Request And Boundary, Current Phone-Side Boundary, Public Package Objective

```text
# CEO Request And Boundary

This input file records the discussion objective and the current runtime
boundary for a future `providers-discuss` run. It is input data only. It is not
an execution log and it must not be treated as provider output.

## Current Phone-Side Boundary

- The CEO is currently on a phone.
- Do not run provider login or OAuth flows now.
- Do not mutate provider home directories, Claude settings, Codex settings,
  hooks, permissions, or workspace trust now.
```

### SRC-0002 - 01-current-package-truth.md

- kind: `text/markdown`
- line_count: `93`
- summary: 01-current-package-truth.md; headings: Current Package Truth, Current Files Of Interest, Existing README Positioning

```text
# Current Package Truth

This file summarizes the current package staging surface for provider seats.
It is derived from local files under:

`closed-door-training/workspaces/kdh-study/providers-discuss-public-package/package-staging/providers-discuss`

## Current Files Of Interest

- `README.md`: English public-facing package draft.
- `install.sh`: local command-link installer; no provider settings mutation.
- `bin/providers-discuss`: package CLI entrypoint.
```

### SRC-0003 - 02-proposed-public-readme-ko-draft.md

- kind: `text/markdown`
- line_count: `72`
- summary: 02-proposed-public-readme-ko-draft.md; headings: providers-discuss 한국어 README 입력 초안, 한 줄 설명, 왜 필요한가

```text
# providers-discuss 한국어 README 입력 초안

이 문서는 공개 패키지의 한국어 설명을 만들기 위한 입력 초안입니다. 아직
공식 README 파일이 아니며, provider discussion에서 검토해야 합니다.

## 한 줄 설명

`providers-discuss`는 여러 AI provider 좌석의 답변을 파일로 남기면서 비교,
반박, 검증, 다음 라운드 프롬프트 개선까지 돕는 로컬 토론 실행 도구입니다.

## 왜 필요한가
```

### SRC-0004 - 03-discussion-run-plan-draft.md

- kind: `text/markdown`
- line_count: `100`
- summary: 03-discussion-run-plan-draft.md; headings: Discussion Run Plan Draft, Draft Run Shape, Draft Rounds

```text
# Discussion Run Plan Draft

This is a draft input plan for the later live run. It must be confirmed by the
CEO before execution.

## Draft Run Shape

- round count: 3
- seat count: 3
- seat A: Claude Team Agents, required
- seat B: Claude Team Agents, required
- seat C: GPT/Codex file-output seat, required
```

### SRC-0005 - 04-terms-podman-docker-sandbox.md

- kind: `text/markdown`
- line_count: `33`
- summary: 04-terms-podman-docker-sandbox.md; headings: Terms: Podman, Docker, Container, Sandbox, Container, Docker

```text
# Terms: Podman, Docker, Container, Sandbox

This file exists because the CEO asked what "pod" means in the current testing
conversation.

## Container

A container is a temporary mini-computer environment for running a program with
its own filesystem view. It is useful for testing how a public package behaves
on a cleaner machine.

## Docker
```

### SRC-0006 - README.en.current.md

- kind: `text/markdown`
- line_count: `258`
- summary: README.en.current.md; headings: providers-discuss, What It Is, What It Is Not

```text
# providers-discuss

`providers-discuss` is a file-backed discussion runner for comparing outputs
from multiple AI provider seats. It records prompts, answers, status files,
proof files, gates, hashes, and orchestrator prompt deltas on disk so a run can
be inspected without trusting chat scrollback.

This package is a staging copy for the future `kodonghui/providers-discuss`
public repository. It is not published yet.

## What It Is
```

## Omitted Files

- none
