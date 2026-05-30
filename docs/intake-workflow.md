# providers-discuss Intake Workflow

This document records the CEO-requested first-run intake behavior for the
public `providers-discuss` package and the KDH alias skill.

## CEO Request Transcript

The requested behavior is:

> 딱 스킬을 쓰면 "언어, 라운드수, seats, 쓸 수 있는 providers(재미나이, 클로드(+team agents), 지피티) 및 각각의 추론 정도, agents의 종류와 각각에 대한 간략한 설명 및 선택한 providers들에 대해 각각 어떤 agents를 쓸건지(또는 default), 주제, brainstorming, input data 경로" 를 정해야한다고 말해줘야 한다.
>
> 예를 들어 "언어(영어, 한국어, 중국어, 일본어, 스페인어 순서로), 라운드 수 -> seats -> providers/efforts 종류 -> ..." 를 정해야 한다고 user에게 이해하기 쉽게 말해줘야 한다.
>
> 맨 처음 언어를 정하라는 부분은 (영어, 한국어, 중국어, 일본어, 스페인어) 순서로 언어 선택을 할 수 있게 각 언어로 설명해야 한다. AGENTS.md에도 5개 국어 중 사용자가 정한 언어로 대화한다고 적어야 한다.
>
> 그 다음 "라운드 수를 입력해주세요" 를 말하고, 라운드 수를 적으면 "seat(좌석 수)를 입력해주세요" 를 말하는 식으로 한 단계씩 진행한다. 각 단계에서 사용자가 이해할 수 있게 간단한 사례를 들어도 된다.
>
> providers/efforts 단계에서는 사용자가 어떤 provider와 effort를 쓸 수 있는지 모를 수 있으므로 옵션을 나열한다. 예: Claude haiku/sonnet/opus 계열, low/medium/high/xhigh/max, Team Agents; GPT/Codex gpt-5.5 계열, low/medium/high/xhigh; Gemini; manual import.
>
> Team Agents도 각 모델과 추론 정도를 정할 수 있다고 알려준다.
>
> agents 단계에서는, 예를 들어 사용자가 Claude 1개와 GPT 1개를 골랐다면 "Claude 1개, GPT 1개 agent를 골라주시거나 default로 하면 됩니다" 라고 설명한다. 그리고 default 및 ideation/architecture 등 agent profiles의 간략한 설명을 보여주고 각각의 provider seat에 어떤 agent를 쓸지 고르게 한다.
>
> 기존 workflow에 없던 언어 정하기와 brainstorming 단계는 추가해야 한다.

## Required Intake Order

The skill should ask one question at a time in this order:

1. Language.
2. Round count.
3. Seat count.
4. Provider, model, effort, and Team Agents usage per seat.
5. Agent profile per selected seat, or `default`.
6. Topic/objective.
7. Brainstorming mode.
8. Input data path.

## Language Prompt

The first prompt should show the language choice in five languages:

- English: Choose a language: English, Korean, Chinese, Japanese, Spanish.
- Korean: 언어를 선택해주세요: 영어, 한국어, 중국어, 일본어, 스페인어.
- Chinese: 请选择语言: 英语, 韩语, 中文, 日语, 西班牙语.
- Japanese: 言語を選んでください: 英語, 韓国語, 中国語, 日本語, スペイン語.
- Spanish: Elige un idioma: inglés, coreano, chino, japonés, español.

After the user chooses a language, continue the intake in that language.

## Provider Option Explanation

Show provider options as availability-dependent examples, then verify with
`auth-preflight` and adapter capability checks:

- Claude: haiku/sonnet/opus-style models when available; efforts
  `low`, `medium`, `high`, `xhigh`, `max`; optional Team Agents.
- GPT/Codex: `gpt-5.5`-style Codex seats when available; efforts
  `low`, `medium`, `high`, `xhigh`.
- Gemini: optional/placeholder until verified; `gemini-latest`-style model.
- Manual: human answer import.

Do not claim an exact model is available until the local provider CLI and
account are checked.

## Agent Profile Explanation

List profiles with one-line descriptions before asking for assignments:

- `default`: use `balanced-kdh`.
- `kdh-ideation-catalyst`: expands early options and reframes the problem.
- `kdh-research-synthesizer`: synthesizes source material into evidence-backed
  conclusions.
- `kdh-system-architect`: turns requirements into architecture and contracts.
- `kdh-code-reviewer`: reviews code, prompts, and contracts for regressions.
- `kdh-qa-verifier`: checks reproducibility and artifact support.
- `kdh-technical-writer`: writes concise user-facing explanations and handoffs.

When the user has selected seats, ask per seat:

```text
You selected:
- Claude: 1 seat
- GPT/Codex: 1 seat

Choose an agent profile for each seat, or choose default.
```

For Claude Team Agents, also ask for teammate roles and optional profile
assignments per teammate.

## Brainstorming Stage

Brainstorming is an explicit stage, not an implicit provider round.

Allowed intake choices:

- `none`: skip brainstorming and start with provider discussion.
- `light`: quick option expansion before R1.
- `deep`: dedicated brainstorming package before provider discussion.

If brainstorming is enabled, record it in config/run notes and include its
output as input to provider rounds.
