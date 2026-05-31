# providers-discuss 한국어 README 입력 초안

이 문서는 공개 패키지의 한국어 설명을 만들기 위한 입력 초안입니다. 아직
공식 README 파일이 아니며, provider discussion에서 검토해야 합니다.

## 한 줄 설명

`providers-discuss`는 여러 AI provider 좌석의 답변을 파일로 남기면서 비교,
반박, 검증, 다음 라운드 프롬프트 개선까지 돕는 로컬 토론 실행 도구입니다.

## 왜 필요한가

채팅 화면만 믿으면 나중에 무엇을 물었고, 누가 어떤 답을 했고, 어떤 근거로
결론이 났는지 추적하기 어렵습니다. `providers-discuss`는 프롬프트, 답변,
상태, proof, claim map, gate, orchestrator review를 모두 파일로 남겨서
나중에 다시 검사할 수 있게 합니다.

## 쉽게 말하면

토론 내용을 머릿속이나 채팅 스크롤에만 두지 않고, 회의록 폴더를 자동으로
정리하는 도구입니다. 각 provider는 한 명의 토론자이고, 각 라운드는 회의의
한 단계입니다. 좋은 주장도 파일과 근거가 없으면 바로 결론이 되지 않습니다.

## 할 수 있는 것

- 몇 라운드로 토론할지 정합니다.
- 몇 개의 좌석을 둘지 정합니다.
- 좌석마다 provider, model, reasoning effort, 역할을 정합니다.
- 입력 폴더를 스캔해서 input pack을 만듭니다.
- manual/import 방식으로 외부 답변을 안전하게 가져올 수 있습니다.
- Codex/GPT, Claude Code, Claude Team Agents, Gemini 같은 provider adapter를
  같은 형식으로 다룰 수 있게 설계되어 있습니다.
- Claude Team Agents는 proof가 있어야 성공으로 인정합니다.
- prompt-only agent profile로 좌석이나 팀원 역할을 정할 수 있습니다.

## 아직 아닌 것

- 모든 provider를 완전 자동으로 안정 실행하는 완성품은 아닙니다.
- OAuth 토큰, 쿠키, provider 설정 파일을 수집하지 않습니다.
- 브라우저나 provider home 폴더를 몰래 읽지 않습니다.
- BMAD, oh-my-agents, KDH agents 같은 외부 agent runtime을 직접 실행하지
  않습니다.
- RAG, 임베딩 DB, 메모리 서버가 아닙니다.

## 추천 첫 사용 흐름

처음에는 manual/import 흐름으로 artifact 계약을 확인하는 것이 가장 안전합니다.

1. `install.sh --dry-run`으로 설치가 무엇을 하는지 확인합니다.
2. `install.sh`로 로컬 CLI 링크를 만듭니다.
3. `providers-discuss config-template` 또는 `providers-discuss configure`로
   설정 파일을 만듭니다.
4. 입력 폴더를 지정합니다.
5. `build-input-pack`으로 입력 자료 목록과 해시를 만듭니다.
6. `init`, `preflight`, `run-round --mode dry-run`으로 구조를 확인합니다.
7. manual answer를 import합니다.
8. claim map을 만들고 `gate`, `orchestrate`, `verify`로 검증합니다.

## 핵심 원칙

- 파일이 진실입니다.
- provider 답변은 바로 결론이 아닙니다.
- Team Agents는 proof가 있어야 성공입니다.
- agent profile은 프롬프트 역할일 뿐, 권한이나 도구를 주지 않습니다.
- live provider 실행보다 먼저 input pack, config, preflight를 확인합니다.

## Provider Discussion에서 검토할 문장

이 패키지를 "자동 토론 봇"처럼 보이게 하면 위험합니다. 대신 "파일 기반,
검증 가능한 provider discussion runner"로 설명하는 편이 맞습니다. 사용자는
provider를 골라 넣을 수 있지만, 각 provider adapter의 현재 성숙도와 로그인
요구사항은 명확히 표시해야 합니다.
