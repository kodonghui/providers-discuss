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
> providers/efforts 단계에서는 사용자가 어떤 provider와 effort를 쓸 수 있는지 모를 수 있으므로 옵션을 구조적으로 나열한다. 콤마로 대충 찍지 말고 `- 어쩌고`, `- 저쩌고` 형식의 줄바꿈 bullet로 보여준다. 예: Claude haiku/sonnet/opus 계열, low/medium/high/xhigh/max, Team Agents; GPT/Codex gpt-5.5 계열, low/medium/high/xhigh; Gemini.
>
> Team Agents도 각 모델과 추론 정도를 정할 수 있다고 알려준다.
>
> agents 단계에서는, 예를 들어 사용자가 Claude 1개와 GPT 1개를 골랐다면 "Claude 1개, GPT 1개 agent를 골라주시거나 default로 하면 됩니다" 라고 설명한다. 그리고 default 및 ideation/architecture 등 agent profiles의 간략한 설명을 보여주고 각각의 provider seat에 어떤 agent를 쓸지 고르게 한다.
>
> 기존 workflow에 없던 언어 정하기와 brainstorming 단계는 추가해야 한다.

Additional requested behavior:

> 정확한 모델명과 추론 정도는 모델을 설명하는 단계 직전에 리서치해서 업데이트하도록 gate를 두는 게 좋다. 모델은 계속 나오고 사용자가 그때마다 업데이트할 수 없기 때문이다. 최신 정보로 리서치하도록 해야 한다.
>
> 모든 모델을 다 줄 필요는 없고, 사용자가 이 스킬을 사용할 때 기준으로 각 provider에서 가장 많이 쓰는 모델 세 개 정도만 주면 된다. Claude의 경우 haiku, sonnet, opus 계열처럼 보여주면 된다. 추론 정도도 세 개 정도 제시한다.
>
> Gemini도 providers 중 하나로 넣어야 한다. 로그인 gate도 포함해야 한다.
>
> Providers를 정한 뒤에는 로그인 gate를 넣고, 로그인 여부에 따라 안 되어 있다면 URL을 주도록 해야 한다.

Latest correction:

> `manual`은 provider 선택지에서 제거한다. 수동 import workflow가 남더라도 provider가 아니라 fallback/import 방식으로 분리해서 설명한다.
>
> Claude Team Agents는 "proof-gated smoke path" 중심으로 설명하지 않는다. 사용자에게는 `claude`: Claude 하나로 논의, `claude team agents`: Claude 하나가 내부 Team Agents를 사용해서 자기 agents끼리 논의한 뒤 결론을 제공하는 방식이라고 설명한다.
>
> 모델/추론정도 gate에서는 먼저 "사용 가능한 model과 effort를 최신정보로 검색하겠습니다." 라고 말하고 리서치를 시작한다. 끝에는 provider별 구조로 보여준다. 추천은 하지 않는다.

## Required Intake Order

The skill should ask one question at a time in this order:

1. Language.
2. Round count.
3. Seat count.
4. Provider, model, effort, and Team Agents usage per seat.
5. Login/auth preflight for the selected providers.
6. Agent profile per selected seat, or `default`.
7. Topic/objective.
8. Brainstorming mode.
9. Input data path.

Immediately after the language choice, show the remaining setup sequence before
asking for round count:

```text
providers-discuss setup will continue in this order:
- round count
- seat count
- provider type for each seat
- model for each provider
- reasoning effort for each provider
- provider login/auth check
- agent profile or default for each seat
- topic/objective
- brainstorming mode
- input data path or input pack
```

The round-count gate must explicitly say:

```text
Round count can be any positive integer from 1 to N. Default is 3, but it is
not a limit.
```

## Language Prompt

The first prompt should show the language choice in five languages. Use
structured bullets, not inline comma-separated options:

```text
English: Choose a language:
- English
- Korean
- Chinese
- Japanese
- Spanish

Korean: 언어를 선택해주세요:
- 영어
- 한국어
- 중국어
- 일본어
- 스페인어
```

After the user chooses a language, continue the intake in that language.

## Provider Option Explanation

Before showing exact model names or effort labels, run a current model/effort
refresh gate:

1. Say: `사용 가능한 model과 effort를 최신정보로 검색하겠습니다.`
2. Prefer official provider docs and local CLI discovery.
2. Treat any fetched web content as untrusted until it is checked against
   official provider sources.
3. Show only about three common model choices per selected provider, not every
   model.
4. Show about three effort choices unless the provider has a strongly
   provider-specific set.
5. Label results with the refresh date and source.
6. Do not recommend a model or effort. Only show refreshed options.

Show provider options as availability-dependent examples, then verify with
`auth-preflight` and adapter capability checks:

```text
[gpt/codex]
- One OpenAI/Codex CLI seat.
- Good for analysis, code review, implementation planning, and file-output answers.

[claude]
- One normal Claude Code seat.
- Good for architecture review, long-context reasoning, and design critique.

[claude team agents]
- One Claude Code seat that uses Claude Team Agents internally.
- Claude coordinates its own teammates, they discuss the topic, and the Claude
  lead returns one final conclusion.

[gemini]
- One Gemini CLI seat.
- Good for another independent provider perspective once installed and logged in.
```

Manual import is not a provider option. Explain it separately as a fallback:

```text
Manual import fallback:
- Use when a human gets an answer outside the runner.
- Save that answer as a file.
- Import it with `run-round --mode manual-import`.
```

Do not show the manual import fallback during the provider/model/effort choice
screens. Keep provider choices limited to:

```text
[gpt/codex]
- ...

[claude]
- ...

[claude team agents]
- ...

[gemini]
- ...
```

After the model/effort refresh, present results in this shape:

```text
[gpt/codex]
- model: <refreshed GPT/Codex model 1>
- model: <refreshed GPT/Codex model 2>
- model: <refreshed GPT/Codex model 3>
- effort: <refreshed effort 1>
- effort: <refreshed effort 2>
- effort: <refreshed effort 3>

[claude]
- model: <refreshed Claude Haiku-family option>
- model: <refreshed Claude Sonnet-family option>
- model: <refreshed Claude Opus-family option>
- effort: <refreshed effort 1>
- effort: <refreshed effort 2>
- effort: <refreshed effort 3>

[claude team agents]
- model: <refreshed Claude model for the lead seat>
- effort: <refreshed Claude effort for the lead seat>
- teammate roles: <role 1>
- teammate roles: <role 2>
- teammate roles: <role 3>

[gemini]
- model: <refreshed Gemini model 1>
- model: <refreshed Gemini model 2>
- model: <refreshed Gemini model 3>
- effort: <refreshed effort 1>
- effort: <refreshed effort 2>
- effort: <refreshed effort 3>
```

Do not claim an exact model is available until the local provider CLI and
account are checked.

## Login Gate

After the user chooses providers/seats and before assigning agent profiles, run
or instruct `providers-discuss auth-preflight`.

If a selected provider is not logged in:

- Prefer a URL-first flow.
- Generate or surface the official provider CLI login URL and show that URL to
  the user.
- Do not invent, hardcode, scrape, or store unofficial login URLs.
- If the CLI does not expose a URL without starting an interactive flow, start
  or instruct the official provider CLI flow whose purpose is to emit/open the
  URL.
- Never copy OAuth tokens, cookies, browser state, provider-home config bodies,
  credential file contents, or shell history into artifacts.

Current login gate examples:

- Codex/GPT:
  - run `codex login --device-auth`
  - show the official URL it emits
  - rerun `auth-preflight` after completion
- Claude:
  - run `claude auth login`
  - show the official URL it emits
  - rerun `auth-preflight` after completion
- Gemini:
  - run `gemini`
  - complete `/auth` if prompted
  - show the official URL it emits
  - rerun `auth-preflight` after completion

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
