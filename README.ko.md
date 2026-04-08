# PKM Briefing Bot

**읽고, 모으고, 요약하고, 연결하고, 제안하고, 스스로 진화하는 — 개인 지식 관리 자동화 시스템**

> Building a Second Brain, 제텔카스텐, 복리 학습, GTD, 그리고 AI-native 워크플로우를 하나의 자동화 파이프라인으로 결합했습니다.

---

## 이 시스템이 하는 일

1. **콘텐츠 캡처** -- `/save <URL>` 한 줄로 웹 글을 저장. AI가 추출, 분류, 태그, 요약, 적용 포인트까지 자동 생성.
2. **모닝 브리핑** -- 오늘 일정 + 뉴스레터 요약 + 주요 이메일 + 액션 아이템 자동 추출.
3. **트렌드 다이제스트** -- Hacker News, Reddit AI, GeekNews에서 수집한 기사를 AI가 5~7개로 큐레이션.
4. **LinkedIn 초안** -- vault 노트 + 트렌드를 조합해 AI가 포스트 초안 작성. 수정 후 바로 게시.
5. **이브닝 리뷰** -- 오후 이메일 요약 + 내일 일정 미리보기.
6. **주간 지식 컴파운딩** -- 이번 주 저장한 노트의 패턴을 발견하고, 프로젝트별 아이디어를 생성.
7. **월간 메타 리뷰** -- 시스템이 스스로를 진단: 수집 편향, 아이디어→코드 전환율, 개선 제안.

---

## 방법론: 왜 이게 작동하는가

### 거인의 어깨 위에서

이 시스템은 검증된 지식 관리 프레임워크들을 AI 자동화로 진화시킨 것입니다.

#### 1. Building a Second Brain (CODE 방법론 -- Tiago Forte)

개인 지식 관리의 4단계: **Capture(캡처) → Organize(정리) → Distill(증류) → Express(표현)**. 이 봇은 네 단계를 모두 자동화합니다:

- **Capture**: `/save`가 웹 콘텐츠를 AI 요약과 함께 구조화
- **Organize**: vault 폴더에 주제별 자동 분류
- **Distill**: Gemini가 뉴스레터, 트렌드, 축적된 지식을 증류
- **Express**: LinkedIn 초안 생성, 주간 리포트, 이메일 다이제스트

#### 2. 제텔카스텐 (Niklas Luhmann의 메모 상자)

루만은 메모 상자 하나로 70권의 책과 400편의 논문을 썼습니다. 비결은 개별 메모가 아니라 **메모 사이의 연결**이었습니다.

주간 리포트가 태그 공통점 분석으로 노트 사이의 실제 연결을 발견합니다 — 태그 2개 이상 공유하는 노트 쌍이 자동 연결되고, AI가 이 프로그래밍적 연결 위에 더 깊은 테마 패턴을 발견합니다.

#### 3. 복리 학습 (Farnam Street -- Shane Parrish)

"지식은 복리처럼 쌓인다. 단, 능동적으로 리뷰하고 연결해야만."

대부분의 사람은 글을 저장하고 다시 보지 않습니다. 주간 리포트는 **지난주 리포트를 입력받아** 패턴을 발견하고, 테마 변화를 추적하고, 프로젝트 아이디어를 제안합니다. 매주 분석이 이전 주 위에 실제로 쌓이는 구조입니다.

#### 4. Getting Things Done (GTD -- David Allen)

"뇌는 아이디어를 만드는 곳이지, 저장하는 곳이 아니다."

모든 이메일 요약과 미팅 준비 노트에서 액션 아이템이 자동 추출됩니다. 모닝 브리핑이 "오늘 해야 할 일"을 직접 인박스를 뒤지지 않아도 보여줍니다.

#### 5. AI-Native 지식 작업 (Karpathy의 LLM OS 개념)

Andrej Karpathy의 비전: LLM을 챗봇이 아니라 **운영체제 레이어**로 사용. 이 봇은 AI를 질문하는 대상이 아니라 백그라운드에서 작동하는 인프라로 취급합니다 -- 이메일을 읽고, vault를 스캔하고, LinkedIn 포스트를 쓰고, 자신의 성능을 진단합니다.

### 기존 도구와 뭐가 다른가

Readwise, Notion AI, Feedly는 각각 퍼즐의 한 조각만 해결합니다. 이 시스템은 이것들을 **닫힌 피드백 루프**로 연결합니다:

```
콘텐츠 저장 --> AI 요약 --> 주간 패턴 발견 --> 프로젝트 아이디어 생성
     ^                                                    |
     |                                                    v
     +-------- 월간 메타 리뷰가 시스템 자체를 진단 <--------+
```

메타 리뷰가 시스템을 진단합니다: 어떤 카테고리를 소홀히 하고 있는지, 어떤 출처가 노이즈인지, AI가 제안한 아이디어가 실제 코드 커밋으로 이어졌는지를 추적합니다 (구조화된 아이디어 상태: 제안 → 구현/폐기).

### 비용 비교

| 도구 | 월 비용 | 제공 기능 |
|-----|---------|----------|
| Readwise | $8 | 하이라이트 동기화 + 복습 |
| Notion AI | $10 | 노트 요약 |
| Feedly Pro | $6 | RSS 수집 |
| **이 봇** | **~$1-3** | **위 전부 + 자동 분석 + 자기 개선** |

*비용: Gemini API (~$1-3/월) + 무료 호스팅 티어 또는 Railway/Docker ~$5/월.*

---

## 빠른 시작

### 방법 1: 가이드 설정 (권장)

```bash
git clone https://github.com/challengekim/pkm-briefing-bot
cd pkm-briefing-bot
pip install -r requirements.txt
python3 setup_wizard.py
python3 main.py --test morning
```

### 방법 2: 수동 설정

1. `config.example.yaml`을 `config.yaml`로 복사하고 값을 채우세요
2. `.env.example`을 `.env`로 복사하고 API 키를 넣으세요
3. `python3 setup_oauth.py --account personal` 실행 (Gmail/Calendar 연동)
4. 테스트: `python3 main.py --test morning`

### 방법 3: Docker

```bash
# 먼저 로컬에서 인증 설정:
python3 setup_wizard.py

# Docker로 실행:
docker-compose up -d
```

> **참고**: OAuth2는 초기 로그인에 브라우저가 필요합니다. `setup_wizard.py`를 로컬에서 먼저 실행한 후, Docker는 생성된 `.env` 파일을 사용합니다.

---

## 설정

모든 설정은 두 파일에 있습니다:

| 파일 | 내용 | 예시 |
|-----|------|-----|
| `config.yaml` | 시크릿 외 모든 설정 | 스케줄, 뉴스레터 발신자, 프로젝트, vault 경로 |
| `.env` | 시크릿만 | API 키, OAuth 토큰 |

전체 옵션은 [`config.example.yaml`](config.example.yaml)을 참조하세요.

---

## 브리핑 종류

| 종류 | 스케줄 | 하는 일 |
|-----|--------|--------|
| 모닝 | 매일 08:00 | 오늘 일정 + 이메일 요약 + 미팅 준비 + 액션 아이템 |
| 트렌드 | 매일 10:00 | HN, Reddit AI, GeekNews 큐레이션 |
| LinkedIn | 매일 11:30 | vault 노트 + 트렌드로 AI 포스트 초안 |
| 이브닝 | 매일 17:00 | 오후 이메일 요약 + 내일 일정 |
| 주간 | 금 18:00 | 주간 회고: 미팅, 이메일, 다음 주 미리보기 |
| 지식 | 토 10:00 | 복리 학습: 이번 주 노트 패턴 + 프로젝트 아이디어 |
| 메타 리뷰 | 매월 1일 | 시스템 자기진단: 수집 패턴, 아이디어→코드 추적 |

모든 스케줄은 `config.yaml`에서 변경 가능합니다.

---

## 아키텍처

```
config.yaml + .env
       |
   config.py          <-- 설정 로더
       |
   +---+----------------------------+
   |  gmail_client    calendar_client|  <-- 데이터 수집
   |  trend_fetcher   knowledge_scanner|
   +---+----------------------------+
       |
   summarizer.py      <-- AI 처리 (Gemini)
       |                  prompts/ko/*.txt
       |                  prompts/en/*.txt
       |
   briefing_composer.py   <-- 포매팅 (순수 HTML)
       |
   +---+---+
   |       |
telegram  email       <-- 전달
```

---

## Obsidian 없이도 됩니다

이 봇은 **아무 마크다운 폴더**에서 동작합니다. Obsidian, Logseq, VS Code, 그냥 텍스트 에디터 -- YAML frontmatter만 있으면 스캐너가 읽을 수 있습니다.

[`vault_template/`](vault_template/)에서 폴더 구조를 확인하세요.

---

## 필요 사항

- Python 3.9+
- Gemini API 키 ([무료 티어 가능](https://aistudio.google.com/apikey))
- Telegram 봇 ([무료, 2분이면 생성](https://core.telegram.org/bots#botfather))
- Google OAuth2 (선택사항, 이메일/캘린더 기능용)

---

## 배포

### 로컬
```bash
python3 main.py
```

### Docker
```bash
docker-compose up -d
```

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

Railway 대시보드에서 환경변수를 설정하고 `config.yaml`을 마운트하세요.

---

## 프롬프트 템플릿

AI 프롬프트는 `prompts/`에 언어별로 관리됩니다:

```
prompts/
  ko/   <-- 한국어 프롬프트
  en/   <-- 영어 프롬프트
```

코드 수정 없이 텍스트 파일만 편집하면 각 브리핑의 톤, 길이, 스타일을 커스터마이즈할 수 있습니다.

---

## Claude Code 스킬 (부가기능)

[Claude Code](https://claude.ai/claude-code) 사용자라면, `/save`, `/learn`, `/recall` 명령어를 터미널에서 바로 사용할 수 있는 스킬 번들이 있습니다:

```bash
cd skills/
bash install.sh
```

자세한 내용은 [`skills/README.md`](skills/README.md)를 참조하세요.

---

## 기여

기여를 환영합니다! 도움이 필요한 영역:

- 추가 LLM 프로바이더 지원 (OpenAI, Claude API)
- 새로운 브리핑 타입
- `prompts/en/` 및 `prompts/ko/` 프롬프트 개선
- 추가 트렌드 소스
- 대체 전달 채널 (Slack, Discord, 이메일 전용)

---

## 라이선스

MIT
