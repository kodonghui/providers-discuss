[English](#english) · [한국어](#korean) · [中文](#chinese) · [日本語](#japanese) · [Español](#spanish)

---

<a id="english"></a>

# providers-discuss

> **Local-first, file-backed runner for multi-provider AI discussions.**
> Compare GPT/Codex, Claude Team Agents, and Gemini side-by-side across structured multi-round debates — with every prompt, answer, proof, and hash written to disk.

---

## Overview

`providers-discuss` is a CLI runner for orchestrating structured discussions across multiple AI providers. Instead of relying on a single provider as the hidden source of truth, it writes every artifact — prompts, answers, logs, proofs, hashes, gate evaluations, and orchestrator deltas — to a local run-state directory you own and can audit.

It is not a billing bypass, a background daemon, or a generic multi-agent framework. It is a transparent, file-backed audit trail for multi-provider reasoning.

---

## Why providers-discuss

On **June 15, 2026**, Anthropic separates Claude Agent SDK and `claude -p` usage into a distinct execution path. Scripts that silently called `claude -p` as an answer-capture path need to be replaced with a runner that owns the artifact contract.

`providers-discuss` is built for this: every dispatch is observable, every answer is traceable, and no provider holds a privileged position over the output record.

---

## Install

```bash
# Preview what the installer will do
./install.sh --dry-run

# Install
./install.sh

# Verify
providers-discuss --help
```

Installs to `$HOME/.local/bin/providers-discuss` and `$HOME/.codex/skills/kdh-providers-discuss`.
Does **not** touch provider homes, OAuth files, Claude hooks, browser settings, cron, or daemons.

```bash
# Optional: add a public alias
./install.sh --with-public-alias

# Uninstall
./install.sh --uninstall

# Run without installing
bin/providers-discuss --help
```

---

## Quick Start

```bash
# 1. Set up environment variables
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

# 2. Validate your config
bin/providers-discuss validate-config "$CONFIG"

# 3. Check provider auth before live dispatch
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"

# 4. Initialize the run state directory
bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 5. Build the input pack
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 6. Advance through rounds
bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch

# 7. Check run status
bin/providers-discuss status "$RUN_ID" --root "$ROOT"

# 8. Verify artifacts and proofs
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

---

## Default Run Shape

`config-template` and `configure` default to a 2-seat run shape so you do not need to restate the standard provider mix each time.

| Seat | Provider / transport | Default model | Effort | Notes |
|---|---|---|---|---|
| `gpt` | `gpt/codex` / `codex_exec_file` | `gpt-5.5` | `xhigh` | Writes a runner-owned answer file and must not use a read-only sandbox |
| `claude_team` | `claude team agents` / `claude_k_team_agents` | `claude-opus-4-8` | `max` | Uses Claude Team Agents with `Ideation Catalyst` included by default |

During interactive `configure`, the setup flow shows this default before the run-shape gate. You can still change round count, seat count, provider type, model, and effort in that gate.

---

## Provider Adapters

| Provider | Transport | Status | Notes |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | ✅ Live headless | Runner-owned answer file + `KDH_CODEX_DONE` marker |
| `claude` | `claude_k` | ⚠️ Smoke-only | Not for production multi-round runs |
| `claude team agents` | `claude_k_team_agents` | ✅ Live | Requires `TeamCreate` / `SendMessage` proof artifacts |
| `gemini` | `gemini_cli` | ✅ Live headless | Child-process workspace trust; JSON/stdout capture |
| *(fallback)* | `manual` | 🔁 Fallback | Import pre-created answer files |

> `claude` (`claude_k`) is a smoke-only path. For live Claude dispatch, use `claude team agents`, which requires durable proof artifacts.

---

## Run Artifacts

The runner writes the following artifact tree for each run. Provider seats produce answer content only — they do not write to event bus, hash, gate, or proof files.

```
.runs/<run-id>/
├── run.json                              # Run metadata and config snapshot
├── events.jsonl                          # Ordered event log
├── inputs/
│   └── input-pack.md                     # Constructed prompt input pack
├── prompts/
│   └── round-R<n>/
│       └── <seat>.prompt.md              # Per-seat prompts
├── answers/
│   └── round-R<n>/
│       └── <seat>.md                     # Provider answers
├── logs/
│   └── round-R<n>/
│       ├── <seat>.status.json            # Dispatch status
│       └── <seat>.proof.json             # Provider proof
├── claims/
│   └── round-R<n>-claim-map.json         # Extracted claims per seat
├── gates/
│   └── round-R<n>-gate.md                # Gate evaluation result
├── orchestrator/
│   └── round-R<n>-review.md              # Orchestrator synthesis
├── result.json                           # Final result
└── verify.json                           # Verification output
```

---

## Agent Profiles

15 bundled prompt-only role contracts. Profiles do not grant tools, credentials, hooks, or filesystem permissions.

| # | Profile |
|---|---|
| 1 | Code Reviewer |
| 2 | Data Analyst |
| 3 | Ideation Catalyst |
| 4 | Implementation Engineer |
| 5 | Knowledge Curator |
| 6 | Orchestrator Planner |
| 7 | Product Strategist |
| 8 | QA Verifier |
| 9 | Release Manager |
| 10 | Research Synthesizer |
| 11 | Security Reviewer |
| 12 | System Architect |
| 13 | Technical Writer |
| 14 | UX Design Reviewer |
| 15 | Web Research Operator |

Profiles are defined in `examples/agents/kdh-profile-catalog.json`.

---

## Deliverable Profiles

Each run can target a deliverable profile. The terminal-round provider must emit its final answer inside a `KDH_FINAL_ARTIFACT` block:

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...content...

<!-- /KDH_FINAL_ARTIFACT -->
```

The terminal gate extracts the block, checks required sections, hashes the artifact, and `finalize` refreshes `result.json`.

| Profile | Description |
|---|---|
| `discussion_summary` | Structured synthesis of the multi-round debate |
| `development_contract` | Engineering scope and interface contract |
| `readme_or_docs` | Documentation artifact |
| `research_synthesis` | Research findings and source attribution |
| `decision_memo` | Decision record with rationale |
| `implementation_plan` | Phased execution plan |

---

## Auth Preflight

Run `auth-preflight` before every live dispatch to catch credential issues early.

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
```

The report records readiness classes only — it never copies OAuth tokens, cookies, provider config bodies, credential files, or shell history.

| Class | Meaning |
|---|---|
| `installed_logged_in` | Ready for live dispatch |
| `installed_not_logged_in` | CLI present but auth needed |
| `missing_cli` | CLI not installed |
| `manual_or_skipped` | Manual import fallback configured |

---

## Claude Team Agents: Proof Requirements

Live dispatch via `claude_k_team_agents` requires all of the following to be recorded as durable proof artifacts:

1. `TeamCreate` must be called and recorded
2. `TaskCreate` must produce real teammate tasks
3. Teammate agents must be launched via the team-scoped `Agent` tool
4. `SendMessage` must appear as real message events — not summaries
5. Summary-only delegation or ordinary subagent delegation without Team Agents evidence → proof verification failure

---

## License

No open-source license has been selected yet. Until a `LICENSE` file is added, the code is visible for inspection but not granted for reuse under any open-source license.

---

---

<a id="korean"></a>

# providers-discuss

> **로컬 우선, 파일 기반 멀티 프로바이더 AI 토론 러너**
> GPT/Codex, Claude Team Agents, Gemini를 구조화된 다중 라운드 토론으로 비교하고, 모든 프롬프트·답변·증명·해시를 디스크에 기록합니다.

---

## 개요

`providers-discuss`는 여러 AI 프로바이더에 걸쳐 구조화된 토론을 오케스트레이션하는 CLI 러너입니다. 단일 프로바이더를 숨겨진 정보 소스로 삼는 대신, 프롬프트·답변·로그·증명·해시·게이트 평가·오케스트레이터 델타 등 모든 아티팩트를 직접 소유하고 감사할 수 있는 로컬 실행 디렉터리에 기록합니다.

과금 우회 수단도, 백그라운드 데몬도, 범용 멀티 에이전트 프레임워크도 아닙니다. 다중 프로바이더 추론을 위한 투명하고 파일 기반의 감사 추적 도구입니다.

---

## 왜 providers-discuss인가

**2026년 6월 15일**, Anthropic은 Claude Agent SDK 및 `claude -p` 사용을 별도의 실행 경로로 분리합니다. `claude -p`를 암묵적으로 호출하던 스크립트는 아티팩트 계약을 직접 소유하는 러너로 대체되어야 합니다.

`providers-discuss`는 바로 이를 위해 만들어졌습니다. 모든 디스패치가 관찰 가능하고, 모든 답변이 추적 가능하며, 어떤 프로바이더도 출력 기록에 대해 특권적 위치를 갖지 않는 러너입니다.

---

## 설치

```bash
# 설치 전 미리보기
./install.sh --dry-run

# 설치
./install.sh

# 확인
providers-discuss --help
```

`$HOME/.local/bin/providers-discuss` 및 `$HOME/.codex/skills/kdh-providers-discuss`에 설치됩니다.
프로바이더 홈, OAuth 파일, Claude 훅, 브라우저 설정, 크론, 데몬은 **변경하지 않습니다**.

```bash
# 퍼블릭 alias 추가 (선택)
./install.sh --with-public-alias

# 제거
./install.sh --uninstall

# 설치 없이 실행
bin/providers-discuss --help
```

---

## 빠른 시작

```bash
# 1. 환경 변수 설정
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

# 2. 설정 파일 유효성 검사
bin/providers-discuss validate-config "$CONFIG"

# 3. 라이브 디스패치 전 프로바이더 인증 확인
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"

# 4. 실행 상태 디렉터리 초기화
bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 5. 입력 팩 구성
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 6. 라운드 진행
bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch

# 7. 실행 상태 확인
bin/providers-discuss status "$RUN_ID" --root "$ROOT"

# 8. 아티팩트 및 증명 검증
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

---

## 기본 실행 형태

`config-template`와 `configure`의 기본값은 2-seat 실행 형태입니다. 그래서 표준 프로바이더 조합을 매번 다시 말하지 않아도 됩니다.

| 시트 | 프로바이더 / 트랜스포트 | 기본 모델 | Effort | 비고 |
|---|---|---|---|---|
| `gpt` | `gpt/codex` / `codex_exec_file` | `gpt-5.5` | `xhigh` | 러너 소유 답변 파일을 쓰며 read-only sandbox를 쓰면 안 됩니다 |
| `claude_team` | `claude team agents` / `claude_k_team_agents` | `claude-opus-4-8` | `max` | Claude Team Agents를 쓰며 `Ideation Catalyst`가 기본 포함됩니다 |

대화형 `configure`에서는 run-shape gate 전에 이 기본값을 먼저 보여줍니다. 그 gate에서 라운드 수, 시트 수, 프로바이더 타입, 모델, effort는 계속 바꿀 수 있습니다.

---

## 지원 프로바이더

| 프로바이더 | 트랜스포트 | 상태 | 비고 |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | ✅ 라이브 헤드리스 | 러너 소유 답변 파일 + `KDH_CODEX_DONE` 마커 |
| `claude` | `claude_k` | ⚠️ 스모크 전용 | 프로덕션 다중 라운드 실행에 적합하지 않음 |
| `claude team agents` | `claude_k_team_agents` | ✅ 라이브 | `TeamCreate` / `SendMessage` 증명 아티팩트 필요 |
| `gemini` | `gemini_cli` | ✅ 라이브 헤드리스 | 자식 프로세스 워크스페이스 신뢰; JSON/stdout 캡처 |
| *(폴백)* | `manual` | 🔁 폴백 | 사전 생성된 답변 파일 임포트 |

> `claude` (`claude_k`)는 스모크 전용입니다. Claude 라이브 디스패치가 필요하면 `claude team agents`를 사용하세요.

---

## 실행 아티팩트

러너는 실행마다 아래 아티팩트 트리를 기록합니다. 프로바이더 시트는 답변 내용만 작성하며, 이벤트 버스·해시·게이트·증명 파일에는 직접 쓰지 않습니다.

```
.runs/<run-id>/
├── run.json                              # 실행 메타데이터 및 설정 스냅샷
├── events.jsonl                          # 이벤트 순서 로그
├── inputs/
│   └── input-pack.md                     # 구성된 프롬프트 입력 팩
├── prompts/
│   └── round-R<n>/
│       └── <seat>.prompt.md              # 시트별 프롬프트
├── answers/
│   └── round-R<n>/
│       └── <seat>.md                     # 프로바이더 답변
├── logs/
│   └── round-R<n>/
│       ├── <seat>.status.json            # 디스패치 상태
│       └── <seat>.proof.json             # 프로바이더 증명
├── claims/
│   └── round-R<n>-claim-map.json         # 시트별 추출된 클레임
├── gates/
│   └── round-R<n>-gate.md                # 게이트 평가 결과
├── orchestrator/
│   └── round-R<n>-review.md              # 오케스트레이터 종합
├── result.json                           # 최종 결과
└── verify.json                           # 검증 출력
```

---

## 에이전트 프로필

프롬프트 전용 역할 계약 15종. 도구·자격 증명·훅·파일시스템 권한은 부여하지 않습니다.

| # | 프로필 |
|---|---|
| 1 | Code Reviewer (코드 리뷰어) |
| 2 | Data Analyst (데이터 분석가) |
| 3 | Ideation Catalyst (아이디에이션 촉진자) |
| 4 | Implementation Engineer (구현 엔지니어) |
| 5 | Knowledge Curator (지식 큐레이터) |
| 6 | Orchestrator Planner (오케스트레이터 플래너) |
| 7 | Product Strategist (제품 전략가) |
| 8 | QA Verifier (QA 검증자) |
| 9 | Release Manager (릴리스 매니저) |
| 10 | Research Synthesizer (리서치 신시사이저) |
| 11 | Security Reviewer (보안 리뷰어) |
| 12 | System Architect (시스템 아키텍트) |
| 13 | Technical Writer (기술 작가) |
| 14 | UX Design Reviewer (UX 디자인 리뷰어) |
| 15 | Web Research Operator (웹 리서치 오퍼레이터) |

정의: `examples/agents/kdh-profile-catalog.json`

---

## 산출물 프로필

마지막 라운드 프로바이더는 최종 답변을 `KDH_FINAL_ARTIFACT` 블록 안에 넣어야 합니다.

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...내용...

<!-- /KDH_FINAL_ARTIFACT -->
```

터미널 게이트가 블록을 추출하고 필수 섹션·해시·`result.json`을 검증합니다.

| 프로필 | 설명 |
|---|---|
| `discussion_summary` | 다중 라운드 토론 구조화 종합 |
| `development_contract` | 엔지니어링 범위 및 인터페이스 계약 |
| `readme_or_docs` | 문서 아티팩트 |
| `research_synthesis` | 리서치 결과 및 출처 귀속 |
| `decision_memo` | 의사결정 기록 및 근거 |
| `implementation_plan` | 단계별 실행 계획 |

---

## 인증 확인

라이브 디스패치 전에 반드시 실행하세요.

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
```

보고서는 준비 상태 클래스만 기록하며, OAuth 토큰·쿠키·프로바이더 설정·자격 증명 파일·셸 히스토리는 절대 복사하지 않습니다.

| 클래스 | 의미 |
|---|---|
| `installed_logged_in` | 라이브 디스패치 준비 완료 |
| `installed_not_logged_in` | CLI 설치됨, 인증 필요 |
| `missing_cli` | CLI 미설치 |
| `manual_or_skipped` | 수동 임포트 폴백 설정됨 |

---

## Claude Team Agents 증명 요건

`claude_k_team_agents` 라이브 디스패치는 다음 모두가 내구성 있는 증명 아티팩트로 기록되어야 합니다.

1. `TeamCreate` 호출 및 기록
2. `TaskCreate`로 실제 팀원 작업 생성
3. 팀원 에이전트를 팀 범위 `Agent` 도구로 실행
4. `SendMessage`가 요약이 아닌 실제 메시지 이벤트로 표시
5. 요약 전용 위임 또는 Team Agents 증거 없는 일반 하위 에이전트 위임 → 증명 검증 실패

---

## 라이선스

아직 오픈소스 라이선스가 선택되지 않았습니다. `LICENSE` 파일이 추가되기 전까지 코드는 검토용으로만 공개되며, 오픈소스 재사용 권한은 부여되지 않습니다.

---

---

<a id="chinese"></a>

# providers-discuss

> **本地优先、基于文件的多提供商 AI 讨论运行器**
> 跨结构化多轮辩论比较 GPT/Codex、Claude Team Agents 和 Gemini，将每一条提示、答案、证明和哈希写入磁盘。

---

## 概述

`providers-discuss` 是一个用于跨多个 AI 提供商编排结构化讨论的 CLI 运行器。它不依赖单一提供商作为隐藏的信息来源，而是将所有制品——提示、答案、日志、证明、哈希、关卡评估和编排器增量——写入您完全掌控、可随时审计的本地运行目录。

它不是绕过计费的工具，不是后台守护进程，也不是通用多智能体框架。它是多提供商推理的透明、基于文件的审计跟踪。

---

## 为什么选择 providers-discuss

**2026年6月15日**，Anthropic 将 Claude Agent SDK 和 `claude -p` 的使用分离为独立的执行路径。静默调用 `claude -p` 的脚本需要被替换为直接拥有制品契约的运行器。

`providers-discuss` 正是为此而生：每次调度都可观测，每条答案都可追溯，没有任何提供商对输出记录拥有特权地位。

---

## 安装

```bash
# 预览安装内容
./install.sh --dry-run

# 安装
./install.sh

# 验证
providers-discuss --help
```

安装至 `$HOME/.local/bin/providers-discuss` 和 `$HOME/.codex/skills/kdh-providers-discuss`。
**不会**修改提供商主目录、OAuth 文件、Claude 钩子、浏览器设置、定时任务或守护进程。

```bash
# 可选：添加公共别名
./install.sh --with-public-alias

# 卸载
./install.sh --uninstall

# 不安装直接运行
bin/providers-discuss --help
```

---

## 快速开始

```bash
# 1. 设置环境变量
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

# 2. 验证配置文件
bin/providers-discuss validate-config "$CONFIG"

# 3. 在实时调度前检查提供商认证
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"

# 4. 初始化运行状态目录
bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 5. 构建输入包
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 6. 推进轮次
bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch

# 7. 查看运行状态
bin/providers-discuss status "$RUN_ID" --root "$ROOT"

# 8. 验证制品与证明
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

---

## 支持的提供商

| 提供商 | 传输 | 状态 | 说明 |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | ✅ 实时无头 | 运行器拥有的答案文件 + `KDH_CODEX_DONE` 标记 |
| `claude` | `claude_k` | ⚠️ 仅烟雾测试 | 不适用于生产多轮运行 |
| `claude team agents` | `claude_k_team_agents` | ✅ 实时 | 需要 `TeamCreate` / `SendMessage` 证明制品 |
| `gemini` | `gemini_cli` | ✅ 实时无头 | 子进程工作区信任；JSON/stdout 捕获 |
| *(回退)* | `manual` | 🔁 回退 | 导入预创建的答案文件 |

> `claude`（`claude_k`）仅为烟雾测试路径。如需 Claude 实时调度，请使用 `claude team agents`。

---

## 运行制品

运行器为每次运行写入以下制品树。提供商席位仅写入答案内容，不直接写入事件总线、哈希、关卡或证明文件。

```
.runs/<run-id>/
├── run.json                              # 运行元数据与配置快照
├── events.jsonl                          # 有序事件日志
├── inputs/
│   └── input-pack.md                     # 构建的提示输入包
├── prompts/
│   └── round-R<n>/
│       └── <seat>.prompt.md              # 各席位提示
├── answers/
│   └── round-R<n>/
│       └── <seat>.md                     # 提供商答案
├── logs/
│   └── round-R<n>/
│       ├── <seat>.status.json            # 调度状态
│       └── <seat>.proof.json             # 提供商证明
├── claims/
│   └── round-R<n>-claim-map.json         # 各席位提取的声明
├── gates/
│   └── round-R<n>-gate.md                # 关卡评估结果
├── orchestrator/
│   └── round-R<n>-review.md              # 编排器综合
├── result.json                           # 最终结果
└── verify.json                           # 验证输出
```

---

## 智能体配置文件

15 种纯提示角色合约。不授予工具、凭据、钩子或文件系统权限。

| # | 配置文件 |
|---|---|
| 1 | Code Reviewer（代码审查员）|
| 2 | Data Analyst（数据分析师）|
| 3 | Ideation Catalyst（创意催化剂）|
| 4 | Implementation Engineer（实现工程师）|
| 5 | Knowledge Curator（知识管理员）|
| 6 | Orchestrator Planner（编排规划师）|
| 7 | Product Strategist（产品策略师）|
| 8 | QA Verifier（QA 验证员）|
| 9 | Release Manager（发布经理）|
| 10 | Research Synthesizer（研究综合员）|
| 11 | Security Reviewer（安全审查员）|
| 12 | System Architect（系统架构师）|
| 13 | Technical Writer（技术文档工程师）|
| 14 | UX Design Reviewer（UX 设计审查员）|
| 15 | Web Research Operator（网络研究操作员）|

定义于 `examples/agents/kdh-profile-catalog.json`。

---

## 交付物配置文件

最终轮次的提供商必须将答案放入 `KDH_FINAL_ARTIFACT` 块。

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...内容...

<!-- /KDH_FINAL_ARTIFACT -->
```

| 配置文件 | 说明 |
|---|---|
| `discussion_summary` | 多轮辩论的结构化综合 |
| `development_contract` | 工程范围与接口契约 |
| `readme_or_docs` | 文档制品 |
| `research_synthesis` | 研究结果与来源归属 |
| `decision_memo` | 带有理由的决策记录 |
| `implementation_plan` | 分阶段执行计划 |

---

## 认证检查

每次实时调度前运行。

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
```

报告仅记录就绪状态，绝不复制 OAuth 令牌、Cookie、提供商配置、凭据文件或 Shell 历史记录。

| 状态 | 含义 |
|---|---|
| `installed_logged_in` | 已准备好实时调度 |
| `installed_not_logged_in` | CLI 已安装，需要登录 |
| `missing_cli` | CLI 未安装 |
| `manual_or_skipped` | 已配置手动导入回退 |

---

## Claude Team Agents 证明要求

`claude_k_team_agents` 实时调度需要以下所有项记录为持久证明制品。

1. 调用并记录 `TeamCreate`
2. `TaskCreate` 生成真实的队友任务
3. 队友智能体通过团队范围的 `Agent` 工具启动
4. `SendMessage` 以真实消息事件（非摘要）呈现
5. 仅摘要委托或无 Team Agents 证据的普通子智能体委托 → 证明验证失败

---

## 许可证

尚未选择开源许可证。在添加 `LICENSE` 文件之前，代码可供查看，但不授予任何开源复用权限。

---

---

<a id="japanese"></a>

# providers-discuss

> **ローカルファースト・ファイルバックドのマルチプロバイダー AI ディスカッションランナー**
> 構造化されたマルチラウンドディスカッションで GPT/Codex、Claude Team Agents、Gemini を比較し、すべてのプロンプト・回答・証明・ハッシュをディスクに書き込みます。

---

## 概要

`providers-discuss` は、複数の AI プロバイダーにわたる構造化ディスカッションをオーケストレーションする CLI ランナーです。単一プロバイダーを隠れた情報源として依存するのではなく、プロンプト・回答・ログ・証明・ハッシュ・ゲート評価・オーケストレーターデルタといったすべてのアーティファクトを、完全に手元で管理・監査できるローカルの実行ディレクトリに書き込みます。

課金回避ツールでも、バックグラウンドデーモンでも、汎用マルチエージェントフレームワークでもありません。マルチプロバイダー推論のための透明でファイルバックドな監査証跡です。

---

## なぜ providers-discuss なのか

**2026年6月15日**、Anthropic は Claude Agent SDK および `claude -p` の使用を別の実行パスに分離します。`claude -p` を暗黙的に呼び出すスクリプトは、アーティファクト契約を直接所有するランナーに置き換える必要があります。

`providers-discuss` はまさにそのために作られました。すべてのディスパッチが観察可能で、すべての回答が追跡可能で、どのプロバイダーも出力記録に対して特権的な地位を持たないランナーです。

---

## インストール

```bash
# インストール内容のプレビュー
./install.sh --dry-run

# インストール
./install.sh

# 確認
providers-discuss --help
```

`$HOME/.local/bin/providers-discuss` と `$HOME/.codex/skills/kdh-providers-discuss` にインストールされます。
プロバイダーホーム、OAuth ファイル、Claude フック、ブラウザ設定、Cron、デーモンは**変更しません**。

```bash
# オプション：パブリックエイリアスを追加
./install.sh --with-public-alias

# アンインストール
./install.sh --uninstall

# インストールせずに実行
bin/providers-discuss --help
```

---

## クイックスタート

```bash
# 1. 環境変数の設定
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

# 2. 設定ファイルの検証
bin/providers-discuss validate-config "$CONFIG"

# 3. ライブディスパッチ前にプロバイダー認証を確認
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"

# 4. 実行状態ディレクトリの初期化
bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 5. 入力パックの構築
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 6. ラウンドの進行
bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch

# 7. 実行状態の確認
bin/providers-discuss status "$RUN_ID" --root "$ROOT"

# 8. アーティファクトと証明の検証
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

---

## 対応プロバイダー

| プロバイダー | トランスポート | ステータス | 備考 |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | ✅ ライブヘッドレス | ランナー所有の回答ファイル + `KDH_CODEX_DONE` マーカー |
| `claude` | `claude_k` | ⚠️ スモークのみ | 本番マルチラウンド実行には不向き |
| `claude team agents` | `claude_k_team_agents` | ✅ ライブ | `TeamCreate` / `SendMessage` 証明アーティファクトが必要 |
| `gemini` | `gemini_cli` | ✅ ライブヘッドレス | 子プロセスワークスペース信頼；JSON/stdout キャプチャ |
| *(フォールバック)* | `manual` | 🔁 フォールバック | 事前作成済み回答ファイルのインポート |

> `claude`（`claude_k`）はスモーク専用です。Claude のライブディスパッチには `claude team agents` を使用してください。

---

## 実行アーティファクト

ランナーは実行ごとに以下のアーティファクトツリーを書き込みます。プロバイダーシートは回答内容のみを書き込み、イベントバス・ハッシュ・ゲート・証明ファイルへの直接書き込みは行いません。

```
.runs/<run-id>/
├── run.json                              # 実行メタデータと設定スナップショット
├── events.jsonl                          # 順序付きイベントログ
├── inputs/
│   └── input-pack.md                     # 構築された入力プロンプトパック
├── prompts/
│   └── round-R<n>/
│       └── <seat>.prompt.md              # シート別プロンプト
├── answers/
│   └── round-R<n>/
│       └── <seat>.md                     # プロバイダー回答
├── logs/
│   └── round-R<n>/
│       ├── <seat>.status.json            # ディスパッチステータス
│       └── <seat>.proof.json             # プロバイダー証明
├── claims/
│   └── round-R<n>-claim-map.json         # シート別抽出クレーム
├── gates/
│   └── round-R<n>-gate.md                # ゲート評価結果
├── orchestrator/
│   └── round-R<n>-review.md              # オーケストレーター総合
├── result.json                           # 最終結果
└── verify.json                           # 検証出力
```

---

## エージェントプロファイル

プロンプト専用ロール契約 15 種。ツール・認証情報・フック・ファイルシステム権限は付与しません。

| # | プロファイル |
|---|---|
| 1 | Code Reviewer（コードレビュアー）|
| 2 | Data Analyst（データアナリスト）|
| 3 | Ideation Catalyst（アイデア触媒）|
| 4 | Implementation Engineer（実装エンジニア）|
| 5 | Knowledge Curator（ナレッジキュレーター）|
| 6 | Orchestrator Planner（オーケストレータープランナー）|
| 7 | Product Strategist（プロダクトストラテジスト）|
| 8 | QA Verifier（QA検証者）|
| 9 | Release Manager（リリースマネージャー）|
| 10 | Research Synthesizer（リサーチシンセサイザー）|
| 11 | Security Reviewer（セキュリティレビュアー）|
| 12 | System Architect（システムアーキテクト）|
| 13 | Technical Writer（テクニカルライター）|
| 14 | UX Design Reviewer（UXデザインレビュアー）|
| 15 | Web Research Operator（ウェブリサーチオペレーター）|

定義場所：`examples/agents/kdh-profile-catalog.json`

---

## 成果物プロファイル

最終ラウンドのプロバイダーは、最終回答を `KDH_FINAL_ARTIFACT` ブロック内に配置してください。

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...内容...

<!-- /KDH_FINAL_ARTIFACT -->
```

| プロファイル | 説明 |
|---|---|
| `discussion_summary` | マルチラウンドディスカッションの構造化要約 |
| `development_contract` | エンジニアリングスコープとインターフェース契約 |
| `readme_or_docs` | ドキュメントアーティファクト |
| `research_synthesis` | 調査結果とソース帰属 |
| `decision_memo` | 根拠を含む意思決定記録 |
| `implementation_plan` | 段階的実行計画 |

---

## 認証確認

ライブディスパッチ前に必ず実行してください。

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
```

レポートは準備状態クラスのみを記録し、OAuth トークン・Cookie・プロバイダー設定・認証情報ファイル・シェル履歴は絶対にコピーしません。

| クラス | 意味 |
|---|---|
| `installed_logged_in` | ライブディスパッチ準備完了 |
| `installed_not_logged_in` | CLI インストール済み、認証が必要 |
| `missing_cli` | CLI 未インストール |
| `manual_or_skipped` | 手動インポートフォールバック設定済み |

---

## Claude Team Agents 証明要件

`claude_k_team_agents` のライブディスパッチには、以下すべてが永続的な証明アーティファクトとして記録される必要があります。

1. `TeamCreate` の呼び出しと記録
2. `TaskCreate` による実際のチームメイトタスクの生成
3. チームメイトエージェントをチームスコープの `Agent` ツール経由で起動
4. `SendMessage` が要約ではなく実際のメッセージイベントとして表示
5. 要約のみの委任または Team Agents 証拠のない通常のサブエージェント委任 → 証明検証失敗

---

## ライセンス

オープンソースライセンスはまだ選択されていません。`LICENSE` ファイルが追加されるまで、コードは確認用に公開されていますが、オープンソースとして再利用する権利は付与されていません。

---

---

<a id="spanish"></a>

# providers-discuss

> **Ejecutor local con respaldo en archivos para discusiones de IA multi-proveedor**
> Compare GPT/Codex, Claude Team Agents y Gemini en debates multi-ronda estructurados, escribiendo cada prompt, respuesta, prueba y hash en disco.

---

## Descripción general

`providers-discuss` es un ejecutor CLI para orquestar discusiones estructuradas entre múltiples proveedores de IA. En lugar de depender de un único proveedor como fuente oculta de verdad, escribe todos los artefactos —prompts, respuestas, logs, pruebas, hashes, evaluaciones de puertas y deltas del orquestador— en un directorio de ejecución local que usted controla y puede auditar.

No es una herramienta para evadir facturación, ni un daemon en segundo plano, ni un framework de agentes genérico. Es un registro de auditoría transparente y basado en archivos para el razonamiento multi-proveedor.

---

## Por qué providers-discuss

El **15 de junio de 2026**, Anthropic separa el uso del Claude Agent SDK y `claude -p` en una ruta de ejecución independiente. Los scripts que llamaban silenciosamente a `claude -p` necesitan ser reemplazados por un ejecutor que posea directamente el contrato de artefactos.

`providers-discuss` fue creado exactamente para esto: cada despacho es observable, cada respuesta es trazable, y ningún proveedor tiene una posición privilegiada sobre el registro de salida.

---

## Instalación

```bash
# Vista previa de lo que instalará
./install.sh --dry-run

# Instalar
./install.sh

# Verificar
providers-discuss --help
```

Se instala en `$HOME/.local/bin/providers-discuss` y `$HOME/.codex/skills/kdh-providers-discuss`.
**No** toca directorios de proveedores, archivos OAuth, hooks de Claude, configuración del navegador, cron ni daemons.

```bash
# Opcional: agregar alias público
./install.sh --with-public-alias

# Desinstalar
./install.sh --uninstall

# Ejecutar sin instalar
bin/providers-discuss --help
```

---

## Inicio rápido

```bash
# 1. Configurar variables de entorno
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

# 2. Validar el archivo de configuración
bin/providers-discuss validate-config "$CONFIG"

# 3. Verificar autenticación de proveedores antes del despacho en vivo
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"

# 4. Inicializar el directorio de estado de ejecución
bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 5. Construir el paquete de entrada
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"

# 6. Avanzar por las rondas
bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch

# 7. Revisar el estado de ejecución
bin/providers-discuss status "$RUN_ID" --root "$ROOT"

# 8. Verificar artefactos y pruebas
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

---

## Proveedores compatibles

| Proveedor | Transporte | Estado | Notas |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | ✅ En vivo sin cabeza | Archivo de respuesta del ejecutor + marcador `KDH_CODEX_DONE` |
| `claude` | `claude_k` | ⚠️ Solo humo | No apto para ejecuciones multi-ronda en producción |
| `claude team agents` | `claude_k_team_agents` | ✅ En vivo | Requiere artefactos de prueba de `TeamCreate` / `SendMessage` |
| `gemini` | `gemini_cli` | ✅ En vivo sin cabeza | Confianza del espacio de trabajo del proceso hijo; captura JSON/stdout |
| *(reserva)* | `manual` | 🔁 Reserva | Importar archivos de respuesta pre-creados |

> `claude`（`claude_k`）es solo para pruebas de humo. Para despacho en vivo de Claude, use `claude team agents`.

---

## Artefactos de ejecución

El ejecutor escribe el siguiente árbol de artefactos en cada ejecución. Los asientos de proveedores escriben solo el contenido de respuesta, sin escribir directamente en el bus de eventos, hashes, puertas ni archivos de prueba.

```
.runs/<run-id>/
├── run.json                              # Metadatos de ejecución y snapshot de configuración
├── events.jsonl                          # Log de eventos ordenados
├── inputs/
│   └── input-pack.md                     # Paquete de entrada de prompts construido
├── prompts/
│   └── round-R<n>/
│       └── <seat>.prompt.md              # Prompts por sede
├── answers/
│   └── round-R<n>/
│       └── <seat>.md                     # Respuestas del proveedor
├── logs/
│   └── round-R<n>/
│       ├── <seat>.status.json            # Estado del despacho
│       └── <seat>.proof.json             # Prueba del proveedor
├── claims/
│   └── round-R<n>-claim-map.json         # Reclamaciones extraídas por sede
├── gates/
│   └── round-R<n>-gate.md                # Resultado de evaluación de puerta
├── orchestrator/
│   └── round-R<n>-review.md              # Síntesis del orquestador
├── result.json                           # Resultado final
└── verify.json                           # Salida de verificación
```

---

## Perfiles de agente

15 contratos de roles solo de prompts. No otorgan herramientas, credenciales, hooks ni permisos de sistema de archivos.

| # | Perfil |
|---|---|
| 1 | Code Reviewer (Revisor de código) |
| 2 | Data Analyst (Analista de datos) |
| 3 | Ideation Catalyst (Catalizador de ideas) |
| 4 | Implementation Engineer (Ingeniero de implementación) |
| 5 | Knowledge Curator (Curador de conocimiento) |
| 6 | Orchestrator Planner (Planificador orquestador) |
| 7 | Product Strategist (Estratega de producto) |
| 8 | QA Verifier (Verificador QA) |
| 9 | Release Manager (Gerente de versiones) |
| 10 | Research Synthesizer (Sintetizador de investigación) |
| 11 | Security Reviewer (Revisor de seguridad) |
| 12 | System Architect (Arquitecto de sistemas) |
| 13 | Technical Writer (Escritor técnico) |
| 14 | UX Design Reviewer (Revisor de diseño UX) |
| 15 | Web Research Operator (Operador de investigación web) |

Definidos en `examples/agents/kdh-profile-catalog.json`.

---

## Perfiles de entregable

El proveedor del último turno debe colocar la respuesta final dentro de un bloque `KDH_FINAL_ARTIFACT`.

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...contenido...

<!-- /KDH_FINAL_ARTIFACT -->
```

| Perfil | Descripción |
|---|---|
| `discussion_summary` | Síntesis estructurada del debate multi-ronda |
| `development_contract` | Alcance de ingeniería y contrato de interfaz |
| `readme_or_docs` | Artefacto de documentación |
| `research_synthesis` | Hallazgos de investigación con atribución de fuentes |
| `decision_memo` | Registro de decisión con justificación |
| `implementation_plan` | Plan de ejecución por fases |

---

## Verificación de autenticación

Ejecutar antes de cada despacho en vivo.

```bash
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
```

El informe solo registra clases de preparación. Nunca copia tokens OAuth, cookies, configuraciones de proveedor, archivos de credenciales ni historial de shell.

| Clase | Significado |
|---|---|
| `installed_logged_in` | Listo para despacho en vivo |
| `installed_not_logged_in` | CLI instalado, se requiere autenticación |
| `missing_cli` | CLI no instalado |
| `manual_or_skipped` | Importación manual configurada |

---

## Requisitos de prueba de Claude Team Agents

El despacho en vivo con `claude_k_team_agents` requiere que todos los elementos siguientes estén registrados como artefactos de prueba persistentes.

1. `TeamCreate` debe ser llamado y registrado
2. `TaskCreate` debe generar tareas reales de compañeros de equipo
3. Los agentes compañeros deben lanzarse mediante la herramienta `Agent` con ámbito de equipo
4. Las llamadas a `SendMessage` deben aparecer como eventos de mensajes reales — no resúmenes
5. Delegación de solo resumen o subagente sin evidencia de Team Agents → fallo de verificación

---

## Licencia

Todavía no se ha seleccionado una licencia de código abierto. Hasta que se agregue un archivo `LICENSE`, el código está visible para inspección pero no se otorga permiso de reutilización bajo ninguna licencia de código abierto.
