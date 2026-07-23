# hermes-wiki-plugin

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

[Hermes Agent](https://github.com/NousResearch/hermes-agent)용 Karpathy LLM Wiki 패턴 플러그인 — 세션에서 wiki 페이지로 자동 변환, 품질 점수, 주제 분류, 엔티티 추출, 세션 간 주제 집계, 7개 언어 i18n 지원.

## 이 플러그인이 필요한 이유

Hermes는 매일 가치 있는 대화를 생성합니다 — 디버깅 세션, 의사결정 토론, 문제 해결, 아이디어 탐색. 하지만 이 지식에는 세 가지 문제가 있습니다:

- **지식이 세션 종료와 함께 사라집니다.** 비슷한 문제에 직면했을 때 "이전에 이런 일을 처리한 적이 있다"고 기억하지만 세부사항을 기억하지 못합니다. `session_search`로 원본 대화를 찾을 수 있지만 결과가 노이즈가 많고 파편화되어 있습니다.
- **구조화된 축적이 없습니다.** 대화는 주제, 의사결정, 결과로 정리된 문서가 아닌 선형 채팅 로그입니다.
- **세션 간 지식을 연결할 수 없습니다.** 서로 다른 세션에서 논의된 동일한 주제나 프로젝트의 다른 단계를 연결할 수 없습니다.

## 기능

플러그인은 세션 종료 시 자동으로 LLM을 호출하여 대화를 구조화된 wiki 페이지로 증류합니다. 여러 세션에서 논의된 주제는 자동으로 주제 페이지로 집계되어 세션 간 통찰력을 보여줍니다.

- **품질 점수** (1-5): 노이즈를 자동 필터링하고 가치 있는 세션만 유지
- **주제 분류 + 엔티티 추출**: "이 대화가 무엇에 관한 것인지" 자동 식별
- **핵심 의사결정 및 문제 해결**: "어떤 의사결정이 내려졌는지, 왜, 문제가 어떻게 해결되었는지" 추출
- **사실 추출**: 재사용 가능한 지식을 장기 기억에 기록하여 향후 검색에서 직접 조회 가능
- **주제 집계**: 세션 간 주제에 대해 LLM 통합 개요, 타임라인, 엔티티, 진화 경로 자동 생성
- **7개 언어 지원**: 대화 언어와 동일한 언어로 wiki 페이지 생성

## 사용 사례

**일일 대화가 지식 베이스를 구축합니다**
기술적 질문을 하거나, 작업 계획을 논의하거나, 새로운 아이디어를 탐색할 때, 각 대화는 자동으로 구조화된 요약을 생성합니다. 시간이 지나면서 wiki는 사용자와 Hermes가 공동 구축한 지식 베이스가 됩니다.

**문제 해결 흔적이 남습니다**
오류를 만나고, 근본 원인을 조사하고, 해결책을 찾는 이 과정이 자동으로 wiki 페이지로 결정됩니다. 다음에 비슷한 문제가 발생하면 채팅 기록을 스크롤하는 것보다 wiki를 검색하는 것이 훨씬 빠릅니다.

**의사결정 기록을 추적할 수 있습니다**
접근 방식을 논의하고, 옵션을 비교하고, 의사결정을 내리는 사고 과정이 자동으로 아카이브됩니다. 나중에 검토할 때 "왜 이 접근 방식을 선택했는지" 명확하게 볼 수 있습니다.

**주제가 세션 간에 진화합니다**
여러 세션에서 동일한 주제(예: 기능 구현, 디버깅 조사)에 대해 작업할 때, 플러그인은 모든 관련 세션의 통찰력을 통합하는 주제 페이지를 자동으로 생성하여 진화 타임라인, 세션 간 의사결정, 패턴을 보여줍니다.

## 설치

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

설치 프로그램은 백엔드를 `~/.hermes/plugins/hermes_wiki/`에, 데스크톱 GUI 플러그인을 `~/.hermes/desktop-plugins/hermes-wiki/`에 배치합니다.

그런 다음 `~/.hermes/config.yaml`을 편집하여 `hermes-wiki`를 플러그인 목록에 추가하세요:

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Hermes Agent를 재시작하여 활성화하세요.

## 작동 방식

**완전 자동 — 수동 단계 불필요.**

```
Hermes와 채팅
  → 세션 종료 (닫기 / 주제 전환 / 리셋)
    → on_session_end 또는 on_session_reset 훅 발동
      → 세션 메시지 읽기
        → LLM 분석: 품질 / 언어 / 주제 / 엔티티 / 의사결정 / 사실
          → wiki 페이지 기록 (품질 >= 4)
          → 사실 추출
          → 영향받는 주제에 대한 더티 마커 기록
  → 1시간 배치 스캔 (훅이 놓친 것 처리)
  → 2시간 주제 집계 (더티 주제 처리)
```

### 세션 워크플로 (Wiki)

1. 세션 종료 → 훅 발동 → 메시지가 SQLite에 대기
2. 백그라운드 스레드가 세션 메시지로 LLM 호출
3. LLM 반환: 품질 점수, 언어, 주제, 엔티티, 핵심 의사결정, 전체 wiki 내용
4. wiki 페이지가 `hermes_wiki_pages`에 기록 (품질 >= 4)
5. 각 주제 슬러그에 대해 더티 마커가 `hermes_wiki_topic_dirty`에 기록

### 주제 워크플로 (주제 집계)

1. 2시간마다 `aggregate_topics()`가 더티 마커 읽기
2. 더티 주제마다 관련 wiki 페이지의 `full_content` 가져오기
3. LLM이 세션 간 콘텐츠 통합: 개요, 의사결정, 패턴, 진화
4. 주제 페이지가 `hermes_wiki_topics`에 기록
5. LLM 성공 시 더티 마커 제거; 폴백 시 재마킹 (다음 사이클에서 재시도)

### 증분 처리

두 워크플로 모두 불필요한 LLM 호출을 피하기 위해 증분 처리를 사용합니다:

- **Wiki**: `hermes_wiki_session_state`가 처리된 세션을 추적; 배치 스캔은 새 세션만 처리
- **Topic**: `hermes_wiki_topic_dirty`가 재집계가 필요한 주제를 표시; 더티 주제만 처리

## 트리거 조건

| 시나리오 | 훅 | wiki 생성 트리거 |
|----------|------|------------------|
| 창 닫기 / 연결 끊김 / 유휴 시간 초과 | `on_session_end` | ✅ 즉시 |
| 주제 전환 / `/new` | `on_session_reset` | ✅ 즉시 |
| 기존 세션에 메시지 추가 | 배치 스캔 | ✅ 1시간 이내 |
| Cron 작업 세션 | — | ❌ 건너뜀 |
| 서브에이전트 세션 | — | ❌ 건너뜀 |
| 메시지 2개 미만 | — | ❌ 건너뜀 |

## 두 가지 모드

플러그인은 시작 시 사용할 모드를 자동 감지합니다:

### 확장 모드 (holographic 메모리 플러그인 활성)
- holographic의 SQLite 연결 공유
- `fact_store(action='search')`가 wiki 결과를 자동 포함
- 추가 도구 불필요 — 한 번의 검색으로 모두 처리

### 독립 모드 (holographic 없음)
- 자체 SQLite 연결 관리
- `wiki_search` 도구로 wiki 페이지 쿼리
- 다른 메모리 플러그인과 독립적으로 작동

## 사용법

### wiki 페이지 검색

**확장 모드** (holographic 활성):
```
You: nginx 설정에 대해 무엇을 논의했나요?
Hermes: [fact_store(action='search', query='nginx') 호출]
  → 사실 + wiki 페이지를 한 번에 반환
```

**독립 모드**:
```
You: wiki에서 nginx 토론을 검색하세요
Hermes: [wiki_search(query='nginx') 호출]
  → 일치하는 wiki 페이지 반환
```

### 데스크톱 GUI

플러그인은 Hermes Desktop에서 듀얼 패널 사이드바를 제공합니다:

- **왼쪽 패널**: 주제 (세션 자식이 있는 접을 수 있는 그룹) + 모든 페이지 (플랫 목록)
- **오른쪽 패널**: 툴바(뒤로, 내보내기, 편집, 삭제), 메타데이터, 콘텐츠가 있는 상세 보기
- **일괄 선택**: 주제와 모든 페이지 모두에서 체크박스가 있는 선택 모드
- **주제 상세**: LLM 통합 개요, 타임라인, 엔티티, 세션 링크 표시

### wiki 페이지 직접 확인

```bash
# 모든 wiki 페이지 나열
sqlite3 ~/.hermes/memory_store.db   "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# 모든 주제 페이지 나열
sqlite3 ~/.hermes/memory_store.db   "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# 집계 대기 중인 더티 주제 확인
sqlite3 ~/.hermes/memory_store.db   "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## 아키텍처

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — 진입점, 훅, 1h 스캔 타이머, 주제 모듈 등록
│   ├── wiki_store.py        — SQLite: hermes_wiki_pages, session_state, pending_queue
│   ├── wiki_builder.py      — LLM 세션 분석 및 wiki 페이지 생성
│   ├── wiki_rpc.py          — wiki.* RPC 메서드 (list, get, create, update, delete, stats)
│   ├── llm_client.py        — 공유 LLM HTTP 클라이언트 (공급자 확인, Anthropic/OpenAI)
│   ├── rpc_utils.py         — 공유 JSON-RPC 유틸리티 (_err, parse_json_columns)
│   ├── topic/
│   │   ├── __init__.py      — 주제 모듈 등록, 2h 집계 타이머
│   │   ├── topic_store.py   — SQLite: hermes_wiki_topics, hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — LLM 주제 집계 (더티 마커 기반 증분 처리)
│   │   └── topic_rpc.py     — topic.* RPC 메서드 (list, get)
│   ├── prompts/
│   │   ├── wiki.md          — session → wiki 프롬프트
│   │   └── topic.md         — 주제 집계 프롬프트
│   └── plugin.yaml          — 플러그인 메타데이터
├── desktop/
│   └── plugin.js            — Hermes Desktop GUI (듀얼 패널 사이드바, DetailToolbar, 일괄 선택)
├── docs/                    — 다국어 README
├── README.md                — 영어 문서
└── install.sh               — 백엔드 + 데스크톱 + 게이트웨이 RPC 패치 설치
```

### 데이터 흐름

```
세션 메시지
  → wiki_builder (LLM) → hermes_wiki_pages (session type)
    → wiki_builder가 더티 마커 기록 → hermes_wiki_topic_dirty
      → topic_builder (LLM)가 wiki 페이지 읽기 → hermes_wiki_topics
        → 데스크톱 GUI가 topic.list / topic.get RPC로 읽기
```

### 데이터베이스 테이블

| 테이블 | 용도 |
|--------|------|
| `hermes_wiki_pages` | 세션 wiki 페이지 (page_type='session') |
| `hermes_wiki_session_state` | 처리된 세션 추적 (증분 wiki) |
| `hermes_wiki_pending_queue` | 처리 대기 중인 세션 큐 |
| `hermes_wiki_topics` | 주제 집계 페이지 (LLM 통합) |
| `hermes_wiki_topic_dirty` | 증분 주제 집계를 위한 더티 마커 |

### RPC 메서드

| 메서드 | 설명 |
|--------|------|
| `wiki.list` | 세션 wiki 페이지 목록 |
| `wiki.get` | 단일 wiki 페이지 조회 |
| `wiki.create` | 수동 wiki 페이지 생성 |
| `wiki.update` | wiki 페이지 업데이트 |
| `wiki.delete` | wiki 페이지 삭제 |
| `wiki.stats` | wiki 통계 |
| `wiki.batch_process` | 대기 세션 일괄 처리 |
| `topic.list` | 주제 페이지 목록 |
| `topic.get` | 세션이 있는 단일 주제 페이지 조회 |

## 기능

- **7개 언어 i18n**: en/zh/ja/ko/de/fr/es
- **품질 점수**: 1-5 척도, 저품질 세션 최소 처리
- **주제 집계**: 세션 간 주제에 대한 LLM 통합 개요, 의사결정, 패턴, 진화 타임라인
- **증분 처리**: 더티 마커로 변경된 주제만 재집계; LLM 실패 시 폴백에서 재시도
- **엔티티 추출**: 대화에서 핵심 엔티티 식별
- **사실 추출**: holographic 메모리에 재사용 가능한 지식 기록
- **데스크톱 GUI**: 듀얼 패널 사이드바, 주제 그룹, 일괄 선택, DetailToolbar, 마크다운 렌더링
- **공유 LLM 클라이언트**: 공급자 확인, Anthropic/OpenAI 형식 감지, .env 로드
- **우아한 성능 저하**: LLM을 사용할 수 없을 때 템플릿으로 폴백; 더티 마커를 통한 재시도

## 문제 해결

**플러그인이 로드되지 않나요?**
- `~/.hermes/config.yaml`에 `hermes-wiki`가 `plugins.enabled`에 있는지 확인
- 로그에서 `hermes-wiki: standalone mode` 또는 `extension mode` 확인
- 디렉토리가 `~/.hermes/plugins/hermes_wiki/`인지 확인 (하이픈이 아닌 밑줄)

**wiki 페이지가 생성되지 않나요?**
- LLM이 구성되어 있는지 확인: config.yaml의 `model.default` 및 `model.provider`
- 로그에서 `hermes-wiki: LLM failed` 확인 — 인증 또는 네트워크 문제
- 세션당 최소 2개 메시지 필요

**주제가 집계되지 않나요?**
- 로그에서 `hermes-wiki: topic aggregation` 메시지 확인
- 더티 마커 확인: `sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- 주제 집계는 2시간마다 실행; 새 주제가 나타나는 데 최대 2시간이 걸릴 수 있음

**wiki_search 도구를 사용할 수 없나요?**
- 독립 모드에서만 사용 가능 (holographic 플러그인 없음)
- 확장 모드에서는 `fact_store(action='search')` 사용

## 라이선스

MIT
