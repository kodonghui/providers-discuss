[English](#english) · [한국어](#korean) · [中文](#chinese) · [日本語](#japanese) · [Español](#spanish)

---

<a id="english"></a>

# providers-discuss

`providers-discuss` is a local, file-backed runner for comparing AI provider
seats across multi-round discussions. It was built for the post-2026-06-15
world where Claude Agent SDK and `claude -p` usage move to a separate monthly
credit path: instead of making one provider CLI the hidden source of truth, the
runner writes prompts, answers, logs, proofs, hashes, gates, source indexes,
and orchestrator deltas to disk.

**It is not a billing bypass. It is an audit trail for multi-provider reasoning.**

## Why Now

On **June 15, 2026**, Anthropic moves Claude Agent SDK and `claude -p` usage
to a separate monthly credit allocation. Scripts that silently called
`claude -p` as an answer-capture path need to be replaced with a runner that
owns the artifact contract. `providers-discuss` is that runner.

## What It Is

- A local CLI for configuring multi-round, multi-seat provider discussions.
- A runner that writes observable artifacts under a run-state directory.
- A live dispatch surface for GPT/Codex, Claude Team Agents, and Gemini
  transports (where the adapter supports live dispatch).
- A manual import fallback for already-captured answer files.
- A read-only agent profile catalog (15 prompt-only roles).
- A gate and verification workflow for claim maps, provider proofs, hashes,
  and final results.

## What It Is Not

- Not a hidden provider automation daemon, cron job, memory system, or RAG
  server.
- Does not collect OAuth tokens, cookies, browser state, or provider-home
  raw config.
- Does not treat direct `claude -p`, direct `codex`, or direct `gemini`
  output as an official provider answer.
- Does not treat dry-run previews, fake proof fixtures, or summary-only Team
  Agents output as live provider success.
- Not a billing bypass.
- Not a generic multi-agent framework or MCP server.
- Not a browser-level provider gateway.

## Install

```bash
./install.sh --dry-run
./install.sh
providers-discuss --help
```

Installs to `$HOME/.local/bin/providers-discuss` and
`$HOME/.codex/skills/kdh-providers-discuss`. Does not touch provider homes,
OAuth files, Claude hooks, browser settings, cron, or daemons.

```bash
# Optional public alias
./install.sh --with-public-alias
# Uninstall
./install.sh --uninstall
# Run without installing
bin/providers-discuss --help
```

## Quick Start: 3-Round, 3-Seat Live Dispatch

```bash
RUN_ID=my-3seat-run
ROOT="$PWD/.runs"
CONFIG=providers-discuss.config.json

bin/providers-discuss validate-config "$CONFIG"
bin/providers-discuss auth-preflight "$CONFIG" --report-dir "$PWD/auth-report"
bin/providers-discuss init --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"
bin/providers-discuss build-input-pack --config "$CONFIG" --root "$ROOT" --run-id "$RUN_ID"
bin/providers-discuss advance "$RUN_ID" --root "$ROOT" --round-mode live-dispatch
bin/providers-discuss status "$RUN_ID" --root "$ROOT"
bin/providers-discuss verify "$RUN_ID" --root "$ROOT"
```

## Provider Adapter Table

| User choice | Transport | Maturity | Notes |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | live headless | runner-owned answer file + `KDH_CODEX_DONE` marker |
| `claude` | `claude_k` | **smoke-only** | interactive Claude Code smoke path; not normal multiround live dispatch |
| `claude team agents` | `claude_k_team_agents` | live team agents | requires TeamCreate / SendMessage proof |
| `gemini` | `gemini_cli` | live headless | child-process workspace trust; JSON/stdout capture |
| fallback | `manual` | fallback | import already-created answers; not a provider choice |

> `claude` (`claude_k`) is smoke-only. Do not treat it as a general live
> dispatch adapter. `claude team agents` (`claude_k_team_agents`) has live
> dispatch but requires durable proof artifacts.

## Agent Profiles

Agent profiles are prompt-only role contracts. The bundled
`examples/agents/kdh-profile-catalog.json` includes 15 profiles (Code
Reviewer, Data Analyst, Ideation Catalyst, Implementation Engineer, Knowledge
Curator, Orchestrator Planner, Product Strategist, QA Verifier, Release
Manager, Research Synthesizer, Security Reviewer, System Architect, Technical
Writer, UX Design Reviewer, Web Research Operator). Profiles do not grant
tools, credentials, hooks, filesystem permissions, or provider-home access.

## Auth and Credential Safety

`auth-preflight` checks selected seats before live work. The report is
sanitized — it records readiness classes (`installed_logged_in`,
`installed_not_logged_in`, `missing_cli`, `manual_or_skipped`) and never
copies OAuth tokens, cookies, provider-home config bodies, credential files,
or shell history.

Gemini live dispatch sets `GEMINI_CLI_TRUST_WORKSPACE=true` only for the child
process and records that in proof artifacts. The runner does not mutate Gemini
provider-home config or copy credentials.

## Team Agents Proof Requirements

Claude Team Agents live dispatch requires durable proof:

- `TeamCreate` must be called and recorded.
- `TaskCreate` must produce real teammate tasks.
- Teammate agents must be launched through the team-scoped `Agent` tool.
- `SendMessage` calls must appear as real message events, not summaries.
- Proof verification fails for summary-only delegation or ordinary subagent
  delegation without Team Agents evidence.

## Runner-Owned Artifacts

The runner owns: prompt construction, answer path assignment, status JSON,
proof JSON, event ordering, artifact hashes, claim/gate/orchestrator
artifacts, and final result and verify outputs. Provider seats produce answer
content only. They must not write event bus, hash, gate, or proof files
directly.

Run artifacts:
`run.json`, `events.jsonl`, `inputs/input-pack.md`,
`prompts/round-Rn/*.prompt.md`, `answers/round-Rn/*.md`,
`logs/round-Rn/*.status.json`, `logs/round-Rn/*.proof.json`,
`claims/round-Rn-claim-map.json`, `gates/round-Rn-gate.md`,
`orchestrator/round-Rn-review.md`, `result.json`, `verify.json`

## Deliverable Profiles

Runs can choose a deliverable profile such as `discussion_summary`,
`development_contract`, `readme_or_docs`, `research_synthesis`,
`decision_memo`, or `implementation_plan`. Profile-backed terminal answers
should emit the final Markdown inside one runner-owned block:

```markdown
<!-- KDH_FINAL_ARTIFACT path="final/development-contract.md" profile="development_contract" -->
# Development Contract

...
<!-- /KDH_FINAL_ARTIFACT -->
```

The terminal gate extracts the block, checks required sections, hashes the
artifact, and lets `finalize` refresh `result.json` from the current final
files.

## Limitations and Release Status

This repository is public early-stage work. Not all adapters have reached
production maturity. `claude_k` is smoke-only. Model names and effort labels
should be refreshed at setup time (`model-refresh`) rather than treated as
stable. Before publishing a stable release, run the verification commands in
`AGENTS.md` and resolve the license blocker.

## License

No open-source license has been selected yet. Until a `LICENSE` file is added,
the code is visible for inspection but not granted for reuse under an
open-source license.

---

<a id="korean"></a>

## 한국어 (Korean)

# providers-discuss

`providers-discuss`는 여러 AI 프로바이더 시트(GPT/Codex, Claude Team Agents,
Gemini)를 다중 라운드 토론으로 비교하기 위한 **로컬 우선, 파일 기반 러너**입니다.

**이 패키지는 과금 우회 수단이 아닙니다. 다중 프로바이더 추론을 위한 감사 추적 도구입니다.**

## 왜 지금인가

**2026년 6월 15일**, Anthropic은 Claude Agent SDK 및 `claude -p` 사용을 별도의
월간 크레딧 경로로 전환합니다. `providers-discuss`는 공식 프로바이더 CLI에
의존하는 대신, 프롬프트·답변·로그·증명·해시·게이트·소스 인덱스·오케스트레이터
델타를 디스크에 기록하는 러너입니다.

## 무엇인가

- 다중 라운드, 다중 시트 프로바이더 토론을 구성하는 로컬 CLI
- 실행 상태 디렉터리 아래에 관찰 가능한 아티팩트를 기록하는 러너
- GPT/Codex, Claude Team Agents, Gemini 트랜스포트용 라이브 디스패치 표면
  (어댑터가 지원하는 경우)
- 이미 캡처된 답변 파일을 위한 수동 임포트 폴백
- 15개의 프롬프트 전용 역할 카탈로그
- 클레임 맵, 프로바이더 증명, 해시, 최종 결과를 위한 게이트·검증 워크플로

## 무엇이 아닌가

- 숨겨진 프로바이더 자동화 데몬, 크론 잡, 메모리 시스템, RAG 서버가 아님
- OAuth 토큰, 쿠키, 브라우저 상태, 프로바이더 홈 설정을 수집하지 않음
- 직접적인 `claude -p`, `codex`, `gemini` 출력을 공식 프로바이더 답변으로
  처리하지 않음
- 드라이런 미리보기, 가짜 증명 픽스처, 요약 전용 Team Agents 출력을 라이브
  프로바이더 성공으로 처리하지 않음
- 과금 우회 수단이 아님
- 범용 멀티 에이전트 프레임워크 또는 MCP 서버가 아님

## 설치

```bash
./install.sh --dry-run
./install.sh
providers-discuss --help
```

## 빠른 시작

```bash
bin/providers-discuss validate-config providers-discuss.config.json
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
bin/providers-discuss init --config providers-discuss.config.json --root ./.runs --run-id my-run
bin/providers-discuss advance my-run --root ./.runs --round-mode live-dispatch
```

## 어댑터 성숙도 표

| 선택 | 트랜스포트 | 성숙도 | 비고 |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | 라이브 헤드리스 | 러너 소유 답변 파일 + `KDH_CODEX_DONE` 마커 |
| `claude` | `claude_k` | **스모크 전용** | 인터랙티브 Claude Code 스모크 경로; 일반 다중 라운드 라이브 디스패치 아님 |
| `claude team agents` | `claude_k_team_agents` | 라이브 팀 에이전트 | TeamCreate / SendMessage 증명 필요 |
| `gemini` | `gemini_cli` | 라이브 헤드리스 | 자식 프로세스 워크스페이스 신뢰; JSON/stdout 캡처 |
| 폴백 | `manual` | 폴백 | 이미 생성된 답변 임포트; 프로바이더 선택이 아님 |

## 에이전트 프로필

에이전트 프로필은 프롬프트 전용 역할 계약입니다. 15개의 프로필(코드 리뷰어,
데이터 분석가, 아이디에이션 카탈리스트, 구현 엔지니어, 지식 큐레이터,
오케스트레이터 플래너, 제품 전략가, QA 검증자, 릴리스 매니저, 리서치 신시사이저,
보안 리뷰어, 시스템 아키텍트, 기술 작가, UX 디자인 리뷰어, 웹 리서치 오퍼레이터).
프로필은 도구, 자격 증명, 훅, 파일시스템 권한 또는 프로바이더 홈 액세스를 부여하지
않습니다.

## 인증 및 자격 증명 안전성

`auth-preflight`는 라이브 작업 전에 선택한 시트를 확인합니다. 보고서는 정제되어
준비 상태 클래스만 기록하며, OAuth 토큰, 쿠키, 프로바이더 홈 설정 본문, 자격 증명
파일 또는 셸 히스토리는 절대 복사하지 않습니다.

Gemini 라이브 디스패치는 `GEMINI_CLI_TRUST_WORKSPACE=true`를 자식 프로세스에만
설정하고 증명 아티팩트에 이를 기록합니다. 러너는 Gemini 프로바이더 홈 설정을
변경하거나 자격 증명을 복사하지 않습니다.

## Team Agents 증명 요건

Claude Team Agents 라이브 디스패치는 내구성 있는 증명이 필요합니다:

- `TeamCreate`가 호출되고 기록되어야 합니다.
- `TaskCreate`가 실제 팀원 작업을 생성해야 합니다.
- 팀원 에이전트는 팀 범위 `Agent` 도구를 통해 실행되어야 합니다.
- `SendMessage` 호출이 요약이 아닌 실제 메시지 이벤트로 나타나야 합니다.
- 요약 전용 위임 또는 Team Agents 증거 없는 일반 하위 에이전트 위임은
  증명 검증 실패로 처리됩니다.

## 러너 소유 아티팩트

러너가 소유하는 것: 프롬프트 구성, 답변 경로 할당, 상태 JSON, 증명 JSON, 이벤트
순서, 아티팩트 해시, 클레임/게이트/오케스트레이터 아티팩트, 최종 결과 및 검증
출력. 프로바이더 시트는 답변 내용만 생성합니다.

## 산출물 프로필

실행은 `discussion_summary`, `development_contract`, `readme_or_docs`,
`research_synthesis`, `decision_memo`, `implementation_plan` 같은 산출물
프로필을 선택할 수 있습니다. 프로필이 있는 마지막 답변은 최종 Markdown을
`KDH_FINAL_ARTIFACT` 블록 안에 넣어야 하며, 러너는 그 블록을 추출하고 필수 섹션,
해시, `result.json`을 검증합니다.

## 한계 및 릴리스 상태

이 저장소는 공개 초기 단계 작업입니다. 모든 어댑터가 프로덕션 성숙도에 도달한
것은 아닙니다. `claude_k`는 스모크 전용입니다. 모델 이름 및 노력 레이블은 안정된
것으로 처리하지 말고 설정 시(`model-refresh`) 새로 고쳐야 합니다.

## 라이선스

아직 오픈소스 라이선스가 선택되지 않았습니다. `LICENSE` 파일이 추가되기 전까지
코드는 검토용으로 공개되어 있지만 오픈소스 재사용 권한은 부여되지 않습니다.

---

<a id="chinese"></a>

## 中文 (Chinese)

# providers-discuss

`providers-discuss` 是一个**本地优先、基于文件**的运行器，用于跨多轮讨论比较
多个 AI 提供商席位（GPT/Codex、Claude Team Agents、Gemini）。

**这不是绕过计费的工具。它是多提供商推理的审计跟踪。**

## 为什么是现在

**2026年6月15日**，Anthropic 将 Claude Agent SDK 和 `claude -p` 的使用迁移到单独
的每月积分路径。`providers-discuss` 的目标是：不依赖单一提供商 CLI 作为隐藏的
真相来源，而是将提示、答案、日志、证明、哈希、关卡、源索引和编排器增量写入
磁盘。

## 它是什么

- 用于配置多轮、多席位提供商讨论的本地 CLI
- 在运行状态目录下写入可观测工件的运行器
- 支持 GPT/Codex、Claude Team Agents 和 Gemini 的实时调度界面（适配器支持时）
- 已捕获答案文件的手动导入回退
- 包含 15 个纯提示角色的目录
- 用于声明映射、提供商证明、哈希和最终结果的关卡与验证工作流

## 它不是什么

- 不是隐藏的提供商自动化守护进程、定时任务、内存系统或 RAG 服务器
- 不收集 OAuth 令牌、Cookie、浏览器状态或提供商主页原始配置
- 不将直接的 `claude -p`、`codex` 或 `gemini` 输出视为官方提供商答案
- 不将干运行预览、虚假证明固件或仅摘要的 Team Agents 输出视为实时提供商成功
- 不是绕过计费的工具
- 不是通用多智能体框架或 MCP 服务器

## 安装

```bash
./install.sh --dry-run
./install.sh
providers-discuss --help
```

## 快速开始

```bash
bin/providers-discuss validate-config providers-discuss.config.json
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
bin/providers-discuss init --config providers-discuss.config.json --root ./.runs --run-id my-run
bin/providers-discuss advance my-run --root ./.runs --round-mode live-dispatch
```

## 适配器成熟度表

| 选择 | 传输 | 成熟度 | 说明 |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | 实时无头 | 运行器拥有的答案文件 + `KDH_CODEX_DONE` 标记 |
| `claude` | `claude_k` | **仅烟雾测试** | 交互式 Claude Code 烟雾路径；非正常多轮实时调度 |
| `claude team agents` | `claude_k_team_agents` | 实时团队智能体 | 需要 TeamCreate / SendMessage 证明 |
| `gemini` | `gemini_cli` | 实时无头 | 子进程工作区信任；JSON/stdout 捕获 |
| 回退 | `manual` | 回退 | 导入已创建的答案；不是提供商选择 |

## 智能体配置文件

智能体配置文件是仅限提示的角色合约。捆绑的目录包含 15 个配置文件。配置文件不
授予工具、凭据、钩子、文件系统权限或提供商主页访问权限。

## 身份验证与凭据安全

`auth-preflight` 在实时工作前检查所选席位。报告经过净化处理——它记录就绪类别，
绝不复制 OAuth 令牌、Cookie、提供商主页配置主体、凭据文件或 Shell 历史记录。

Gemini 实时调度仅为子进程设置 `GEMINI_CLI_TRUST_WORKSPACE=true`，并在证明工件
中记录这一点。运行器不会更改 Gemini 提供商主页配置或复制凭据。

## Team Agents 证明要求

Claude Team Agents 实时调度需要持久证明：

- 必须调用并记录 `TeamCreate`。
- `TaskCreate` 必须创建真实的队友任务。
- 队友智能体必须通过团队范围的 `Agent` 工具启动。
- `SendMessage` 调用必须作为真实消息事件出现，而非摘要。
- 仅摘要委托或无 Team Agents 证据的普通子智能体委托将导致证明验证失败。

## 运行器拥有的工件

运行器拥有：提示构建、答案路径分配、状态 JSON、证明 JSON、事件排序、工件哈希、
声明/关卡/编排器工件以及最终结果和验证输出。提供商席位仅生成答案内容。

## 交付物配置文件

运行可以选择 `discussion_summary`、`development_contract`、
`readme_or_docs`、`research_synthesis`、`decision_memo` 或
`implementation_plan` 等交付物配置文件。带配置文件的最终答案应将最终
Markdown 放入 `KDH_FINAL_ARTIFACT` 块中；运行器会提取该块、检查必需章节、
记录哈希，并刷新 `result.json`。

## 限制和发布状态

此存储库为公开早期阶段工作。并非所有适配器都已达到生产成熟度。`claude_k`
仅为烟雾测试模式。模型名称和工作量标签应在设置时（`model-refresh`）刷新，
而非视为稳定。

## 许可证

目前尚未选择开源许可证。在添加 `LICENSE` 文件之前，代码可供查看，但不授予
开源复用权限。

---

<a id="japanese"></a>

## 日本語 (Japanese)

# providers-discuss

`providers-discuss` は、複数の AI プロバイダーシート（GPT/Codex、Claude Team
Agents、Gemini）をマルチラウンドディスカッションで比較するための
**ローカルファースト・ファイルバックドランナー**です。

**これは課金回避ツールではありません。マルチプロバイダー推論の監査証跡です。**

## なぜ今なのか

**2026年6月15日**、Anthropic は Claude Agent SDK および `claude -p` の使用を
別の月次クレジットパスに移行します。`providers-discuss` は、単一のプロバイダー
CLI を隠れた情報源とするのではなく、プロンプト・回答・ログ・証明・ハッシュ・
ゲート・ソースインデックス・オーケストレーターデルタをディスクに書き込む
ランナーです。

## 何であるか

- マルチラウンド・マルチシートのプロバイダーディスカッションを設定する
  ローカル CLI
- 実行状態ディレクトリ配下に観察可能なアーティファクトを書き込むランナー
- GPT/Codex、Claude Team Agents、Gemini トランスポートのライブディスパッチ
  サーフェス（アダプターが対応している場合）
- 既にキャプチャされた回答ファイルのための手動インポートフォールバック
- 15 のプロンプト専用ロールカタログ
- クレームマップ、プロバイダー証明、ハッシュ、最終結果のためのゲートと
  検証ワークフロー

## 何でないか

- 隠れたプロバイダー自動化デーモン、Cronジョブ、メモリシステム、RAGサーバー
  ではない
- OAuth トークン、Cookie、ブラウザ状態、プロバイダーホームの生設定を
  収集しない
- 直接の `claude -p`、`codex`、`gemini` 出力を公式プロバイダー回答として扱わない
- ドライランプレビュー、偽の証明フィクスチャ、要約のみの Team Agents 出力を
  ライブプロバイダー成功として扱わない
- 課金回避ツールではない
- 汎用マルチエージェントフレームワークや MCP サーバーではない

## インストール

```bash
./install.sh --dry-run
./install.sh
providers-discuss --help
```

## クイックスタート

```bash
bin/providers-discuss validate-config providers-discuss.config.json
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
bin/providers-discuss init --config providers-discuss.config.json --root ./.runs --run-id my-run
bin/providers-discuss advance my-run --root ./.runs --round-mode live-dispatch
```

## アダプター成熟度テーブル

| 選択 | トランスポート | 成熟度 | 備考 |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | ライブヘッドレス | ランナー所有の回答ファイル + `KDH_CODEX_DONE` マーカー |
| `claude` | `claude_k` | **スモークのみ** | インタラクティブ Claude Code スモークパス；通常のマルチラウンドライブディスパッチではない |
| `claude team agents` | `claude_k_team_agents` | ライブチームエージェント | TeamCreate / SendMessage 証明が必要 |
| `gemini` | `gemini_cli` | ライブヘッドレス | 子プロセスワークスペース信頼；JSON/stdout キャプチャ |
| フォールバック | `manual` | フォールバック | 作成済み回答のインポート；プロバイダー選択ではない |

## エージェントプロファイル

エージェントプロファイルはプロンプト専用のロール契約です。バンドルされたカタログには
15 のプロファイルが含まれています。プロファイルはツール、認証情報、フック、ファイル
システム権限、またはプロバイダーホームアクセスを付与しません。

## 認証とクレデンシャルの安全性

`auth-preflight` はライブ作業前に選択したシートを確認します。レポートはサニタイズ
されており、OAuth トークン、Cookie、プロバイダーホーム設定本体、認証情報ファイル、
またはシェル履歴は決してコピーされません。

Gemini ライブディスパッチは `GEMINI_CLI_TRUST_WORKSPACE=true` を子プロセスにのみ
設定し、証明アーティファクトにそれを記録します。ランナーは Gemini プロバイダー
ホーム設定を変更したり、認証情報をコピーしたりしません。

## Team Agents 証明要件

Claude Team Agents ライブディスパッチには永続的な証明が必要です：

- `TeamCreate` が呼び出され、記録されなければなりません。
- `TaskCreate` が実際のチームメイトタスクを生成しなければなりません。
- チームメイトエージェントはチームスコープの `Agent` ツールを通じて起動されなければ
  なりません。
- `SendMessage` 呼び出しは要約ではなく、実際のメッセージイベントとして表示されなければ
  なりません。
- 要約のみの委任や Team Agents 証拠のない通常のサブエージェント委任は証明検証失敗
  となります。

## ランナー所有アーティファクト

ランナーが所有するもの：プロンプト構築、回答パス割り当て、ステータス JSON、
証明 JSON、イベント順序、アーティファクトハッシュ、クレーム/ゲート/オーケスト
レーターアーティファクト、最終結果および検証出力。プロバイダーシートは回答内容
のみを生成します。

## 成果物プロファイル

実行では `discussion_summary`、`development_contract`、`readme_or_docs`、
`research_synthesis`、`decision_memo`、`implementation_plan` などの成果物
プロファイルを選択できます。プロファイル付きの最終回答は、最終 Markdown を
`KDH_FINAL_ARTIFACT` ブロックに入れます。ランナーはそのブロックを抽出し、必須
セクション、ハッシュ、`result.json` を検証します。

## 制限事項とリリース状況

このリポジトリは公開初期段階の作業です。すべてのアダプターが本番環境の成熟度に
達しているわけではありません。`claude_k` はスモーク専用です。モデル名および
エフォートラベルは安定したものとして扱わず、設定時（`model-refresh`）に更新して
ください。

## ライセンス

オープンソースライセンスはまだ選択されていません。`LICENSE` ファイルが追加される
までは、コードは確認用に公開されていますが、オープンソースとして再利用する権利は
付与されていません。

---

<a id="spanish"></a>

## Español (Spanish)

# providers-discuss

`providers-discuss` es un **ejecutor local con respaldo en archivos** para
comparar múltiples sedes de proveedores de IA (GPT/Codex, Claude Team Agents,
Gemini) en discusiones de múltiples rondas.

**No es una herramienta para evadir facturación. Es un registro de auditoría
para razonamiento multi-proveedor.**

## Por qué ahora

El **15 de junio de 2026**, Anthropic migra el uso del Claude Agent SDK y
`claude -p` a una ruta de crédito mensual separada. `providers-discuss` fue
creado para este mundo post-2026-06-15: en lugar de hacer de un CLI de
proveedor la fuente oculta de verdad, el ejecutor escribe en disco los
prompts, respuestas, registros, pruebas, hashes, puertas, índices de fuentes
y deltas del orquestador.

## Qué es

- Una CLI local para configurar discusiones de proveedores en múltiples rondas
  y múltiples sedes.
- Un ejecutor que escribe artefactos observables bajo un directorio de estado
  de ejecución.
- Una superficie de despacho en vivo para transportes GPT/Codex, Claude Team
  Agents y Gemini (donde el adaptador lo soporte).
- Un mecanismo de importación manual para archivos de respuesta ya capturados.
- Un catálogo de 15 perfiles de roles solo de prompts.
- Un flujo de trabajo de puertas y verificación para mapas de reclamaciones,
  pruebas de proveedores, hashes y resultados finales.

## Qué no es

- No es un demonio de automatización de proveedores oculto, tarea cron,
  sistema de memoria ni servidor RAG.
- No recopila tokens OAuth, cookies, estado del navegador ni configuración
  sin procesar del proveedor.
- No trata la salida directa de `claude -p`, `codex` o `gemini` como respuesta
  oficial del proveedor.
- No trata las vistas previas de simulacro, los accesorios de prueba falsos
  o la salida de Team Agents de solo resumen como éxito de proveedor en vivo.
- No es una herramienta para evadir facturación.
- No es un framework de agentes múltiples genérico ni un servidor MCP.

## Instalación

```bash
./install.sh --dry-run
./install.sh
providers-discuss --help
```

## Inicio rápido

```bash
bin/providers-discuss validate-config providers-discuss.config.json
bin/providers-discuss auth-preflight providers-discuss.config.json --report-dir ./auth-report
bin/providers-discuss init --config providers-discuss.config.json --root ./.runs --run-id my-run
bin/providers-discuss advance my-run --root ./.runs --round-mode live-dispatch
```

## Tabla de madurez de adaptadores

| Elección | Transporte | Madurez | Notas |
|---|---|---|---|
| `gpt/codex` | `codex_exec_file` | en vivo sin cabeza | archivo de respuesta del ejecutor + marcador `KDH_CODEX_DONE` |
| `claude` | `claude_k` | **solo humo** | ruta de humo de Claude Code interactivo; no despacho en vivo multirronda normal |
| `claude team agents` | `claude_k_team_agents` | agentes de equipo en vivo | requiere prueba de TeamCreate / SendMessage |
| `gemini` | `gemini_cli` | en vivo sin cabeza | confianza del espacio de trabajo del proceso hijo; captura JSON/stdout |
| reserva | `manual` | reserva | importar respuestas ya creadas; no es una elección de proveedor |

## Perfiles de agente

Los perfiles de agente son contratos de roles solo de prompts. El catálogo
incluye 15 perfiles. Los perfiles no otorgan herramientas, credenciales,
hooks, permisos de sistema de archivos ni acceso al proveedor principal.

## Seguridad de autenticación y credenciales

`auth-preflight` verifica los asientos seleccionados antes del trabajo en
vivo. El informe está saneado: registra las clases de preparación y nunca
copia tokens OAuth, cookies, cuerpos de configuración del proveedor,
archivos de credenciales ni historial de shell.

El despacho en vivo de Gemini establece `GEMINI_CLI_TRUST_WORKSPACE=true`
solo para el proceso hijo y lo registra en los artefactos de prueba. El
ejecutor no muta la configuración del proveedor Gemini ni copia credenciales.

## Requisitos de prueba de Team Agents

El despacho en vivo de Claude Team Agents requiere prueba duradera:

- `TeamCreate` debe ser llamado y registrado.
- `TaskCreate` debe producir tareas reales de compañeros de equipo.
- Los agentes compañeros deben lanzarse a través de la herramienta `Agent`
  con ámbito de equipo.
- Las llamadas a `SendMessage` deben aparecer como eventos de mensajes reales,
  no resúmenes.
- La delegación de solo resumen o la delegación de subagente ordinaria sin
  evidencia de Team Agents resulta en falla de verificación de prueba.

## Artefactos del ejecutor

El ejecutor posee: construcción de prompts, asignación de rutas de respuesta,
JSON de estado, JSON de prueba, ordenación de eventos, hashes de artefactos,
artefactos de reclamación/puerta/orquestador y salidas de resultado y
verificación finales. Los asientos de proveedores producen solo contenido de
respuesta.

## Perfiles de entregable

Una ejecución puede elegir perfiles de entregable como `discussion_summary`,
`development_contract`, `readme_or_docs`, `research_synthesis`,
`decision_memo` o `implementation_plan`. Las respuestas finales con perfil
deben colocar el Markdown final dentro de un bloque `KDH_FINAL_ARTIFACT`; el
ejecutor extrae ese bloque, revisa secciones requeridas, registra hashes y
actualiza `result.json`.

## Limitaciones y estado de lanzamiento

Este repositorio es trabajo público en etapa temprana. No todos los adaptadores
han alcanzado madurez de producción. `claude_k` es solo de humo. Los nombres
de modelos y etiquetas de esfuerzo deben actualizarse en el momento de la
configuración con `model-refresh` en lugar de tratarlos como estables.

## Licencia

Todavía no se ha seleccionado una licencia de código abierto. Hasta que se
agregue un archivo `LICENSE`, el código está visible para inspección, pero no
se concede permiso de reutilización como código abierto.
