# Compound Brain

**"나중에 읽기"로 저장만 하고 안 보는 사람을 위한 시스템.**

저장한 글을 대신 읽고, 패턴을 찾고, 매주 복리 분석해주는 봇입니다.

---

## 빠른 시작

**로컬에서 실행. macOS, Linux, Windows. 서버 필요 없음.**

### macOS / Linux

```bash
bash <(curl -s https://raw.githubusercontent.com/challengekim/compound-brain/main/install.sh)
```

### Windows

```powershell
git clone https://github.com/challengekim/compound-brain
cd compound-brain
pip install -r requirements.txt
python setup_wizard.py
python main.py
```

### 설정 마법사가 안내하는 것

- **LLM 선택** — Ollama (API key 불필요, $0) / Gemini (무료 키) / OpenRouter / OpenAI / Claude
- **텔레그램 봇** — 생성 가이드 + chat ID 자동 감지
- **vault 폴더** — 저장한 글이 쌓이는 곳

---

## 글 저장 (5가지 방법)

| 방법 | 어디서 | 어떻게 |
|------|--------|--------|
| **텔레그램** | 폰 / 데스크탑 | 봇에 URL 전송 |
| **Claude Code** | 터미널 | `/save <URL>` — AI가 추출 + 요약 + 분류 + 태그 + 적용 포인트 |
| **CLI** | 터미널 | `python3 main.py --save <URL>` |
| **자동** | 매일 실행 | 트렌드 상위 3개가 vault에 자동 저장 |
| **수동** | 아무 에디터 | YAML frontmatter 포함 `.md` 파일 생성 |

---

## 저장 후 봇이 하는 일

| 브리핑 | 스케줄 | 하는 일 |
|--------|--------|---------|
| **트렌드** | 매일 10:00 | HN/Reddit/GeekNews에서 AI가 5~7개 큐레이션 |
| **LinkedIn** | 매일 11:30 | vault 노트 + 트렌드로 초안 생성 |
| **주간 복리** | 토 10:00 | 최근 4주 리포트가 이번 주 입력. 태그 연결. 프로젝트 아이디어. |
| **월간 메타** | 매월 1일 | 수집 편향 + 아이디어→코드 추적 (AI 추정) |

스케줄은 `config.yaml`에서 변경 가능.

---

## 복리 학습 작동 방식 (실제 예시)

**1주차** — 글 7개 저장.
```
→ 3개 테마: "에이전트 아키텍처", "AI-native 조직", "토큰 최적화"
→ 제안: "토큰 최적화를 프로젝트 API 비용에 적용"
```

**3주차** — 이전 리포트가 분석에 입력됨.
```
→ "관심사가 아키텍처 → 실용적 워크플로우로 진화 중"
→ 노트 자동 연결: "마케팅 자동화" ↔ "에이전트 오케스트레이션" (공통 태그)
→ 프로젝트 교차 제안 생성
```

**8주차** — 50개 이상 누적.
```
→ 8주 학습 궤적이 보임
→ "2주차 프레임워크를 사이드 프로젝트 추천 엔진에 적용 가능"
```

**월말** — 메타 리뷰.
```
→ "78개 노트. AI Engineering 40%, Business 25%, Marketing 20%"
→ "제안 12개 중 3개가 실제 코드가 됨 — 25% 전환율"
→ "사각지대: DevOps 카테고리 없음. 다양화 필요."
```

**이 시스템 없이**: 읽고 → 잊고 → 또 읽음
**이 시스템으로**: 저장 → 분석 → 패턴 누적 → 실행 추적

*(실제 vault 데이터로 10주 시뮬레이션 결과)*

---

## 어떻게 만들었나

하나의 아이디어가 아닙니다. 수십 개 오픈소스와 방법론을 리서치하고, **어떻게 조합해야 지식이 실제로 복리로 쌓이는지** 고민해서 만든 시스템입니다.

### 참고한 프로젝트

| 프로젝트 | 영향 |
|---------|------|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | LLM 변이 루프로 자기 개선 |
| [VoidLight00/autoimprove-cc](https://github.com/VoidLight00/autoimprove-cc) | Binary eval + 스킬 자동 수정 |
| [olelehmann100kMRR/autoresearch-skill](https://github.com/olelehmann100kMRR/autoresearch-skill) | 95%+ 변이 목표 |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 멀티 플랫폼 트렌드 리서치 |
| [Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) | /wiki, /skill-eval, /save 스킬 |

### 참고한 아티클

| 글 | 핵심 |
|----|------|
| [Karpathy — LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595) | LLM이 .md 위키 컴파일 (RAG 아님) |
| [unclejobs-ai — LLM Wiki 가이드](https://gist.github.com/unclejobs-ai/7af4a9e3446751b8e2c3bc66d23fa0ac) | 실전 위키 구현 |
| [Simpson Sim — 복리 지식 시스템](https://retn.kr/blog/compound-learning-ai-system/) | 4단계 루프: 수집→구조화→맥락부여→적용 |

### 기반 이론
- **BASB** (Tiago Forte) — 캡처→정리→증류→표현, 4단계 자동화
- **제텔카스텐** (루만) — 태그 공통점 분석으로 노트 자동 연결
- **GTD** (David Allen) — 콘텐츠에서 액션 자동 추출

### 생태계

| 레이어 | 역할 | 독립 실행? |
|--------|------|:---------:|
| **Compound Brain** (이 레포) | 브리핑 + 트렌드 + 복리 분석 + 메타 리뷰 | Yes |
| **Claude Code + OMC** | /save, /wiki, /skill-eval, /learn | [Claude Code](https://claude.ai/claude-code) 필요 |
| **마크다운 Vault** | 저장소 (Obsidian, Logseq, VS Code, 아무 폴더) | Yes |

> 봇은 독립 동작합니다. Claude Code는 선택사항.

### vs. 기존 도구

| 도구 | 월 비용 | 부족한 것 | Compound Brain |
|-----|---------|----------|----------------|
| Readwise | $8 | 노트 간 분석 없음 | 패턴 발견 |
| Notion AI | $10 | 노트가 고립됨 | 태그 연결 + 주간 연속성 |
| Feedly | $6 | 그냥 나열 | 프로젝트 맥락 기반 큐레이션 |
| **이 봇** | **$0** | | **위 전부 + 복리 분석** |

---

## 설정

| 파일 | 내용 |
|-----|------|
| `config.yaml` | 스케줄, 프로젝트, vault 경로, LLM |
| `.env` | API 키, 봇 토큰 |

→ [`config.example.yaml`](config.example.yaml) 참조

---

## 필요 사항

- Python 3.9+ (macOS, Linux, Windows)
- Telegram 봇 ([무료, 2분](https://core.telegram.org/bots#botfather))
- **하나 선택**: [Ollama](https://ollama.com) ($0, 로컬) / [Gemini](https://aistudio.google.com/apikey) ($0, 무료 키) / OpenRouter / OpenAI / Claude

---

## 백그라운드 / Docker

```bash
nohup python3 main.py &                              # macOS/Linux
Start-Process python main.py -WindowStyle Hidden      # Windows
docker-compose up -d                                   # Docker
```

---

## 업데이트

```bash
cd compound-brain && git pull
pip install -r requirements.txt    # 의존성 변경 시에만
```

`config.yaml`, `.env`, vault는 건드리지 않음.

---

## 기여

[CONTRIBUTING.md](CONTRIBUTING.md) 참조. 문의: [Issues](https://github.com/challengekim/compound-brain/issues) 또는 kimtaewoo1201@gmail.com

## 라이선스

MIT
