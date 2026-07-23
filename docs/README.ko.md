# hermes-wiki-plugin

[Hermes Agent](https://github.com/NousResearch/hermes-agent)용 Karpathy LLM Wiki 패턴 플러그인 — 세션에서 wiki 페이지로 자동 변환, 품질 점수, 주제 분류, 엔티티 추출, 7개 언어 i18n 지원.

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## 이 플러그인이 필요한 이유

Hermes는 매일 많은 가치 있는 대화를 생성합니다——디버깅, 의사결정 토론, 문제 해결, 아이디어 탐색. 하지만 이 지식에는 세 가지 문제가 있습니다:

- **세션이 끝나면 지식이 가라앉습니다.** 다음에 비슷한 문제를 만나면 "전에 이런 걸 한 적이 있었는데"라고만 기억할 뿐 세부사항을 기억하지 못합니다. `session_search`로 원본 대화를 검색할 수 있지만 노이즈가 많고 문맥이 단편화되어 있습니다.
- **구조화된 축적이 없습니다.** 대화는 선형적인 채팅 로그이며, 주제·결론·결론별로 정리된 문서가 아닙니다.
- **세션 간 지식을 연결할 수 없습니다.** 같은 주제가 다른 세션에서 논의되거나, 같은 프로젝트의 다른 단계를 연결할 수 없습니다.

## 이 플러그인의 기능

세션이 끝나면 자동으로 LLM을 호출하여 대화를 구조화된 wiki 페이지로 정제합니다:

- **품질 점수** (1-5): 노이즈를 자동 필터링하여 가치 있는 세션만 유지
- **주제 분류 + 엔티티 추출**: "이 대화가 무엇에 관한 것인지"를 자동 식별
- **핵심 결정 및 문제 해결**: "어떤 결정을 내렸고, 왜, 어떻게 문제를 해결했는지"를 추출
- **Fact 추출**: 재사용 가능한 지식(도구의 특성, 함정, 워크플로 발견)을 장기 메모리에 기록하여 향후 검색에서 직접 히트
- **7개 언어 지원**: 대화와 같은 언어로 wiki 페이지 생성

## 사용 사례

**일상 대화가 지식 베이스로**
기술적인 질문이든, 업무 계획 토론이든, 새로운 아이데어 탐색이든, 각 대화가 끝날 때 자동으로 구조화된 요약이 생성됩니다. 시간이 지남에 따라 wiki는 당신과 Hermes가 함께 구축하는 지식 베이스가 됩니다.

**문제 해결이 흔적을 남김**
오류 발생, 원인 조사, 해결책 발견——이 과정이 자동으로 wiki 페이지로 결정화됩니다. 다음에 비슷한 문제가 발생했을 때, wiki를 검색하는 것이 채팅 기록을 스크롤하는 것보다 훨씬 빠릅니다.

**의사결정 이력이 추적 가능**
접근 방식 토론, 선택지 비교, 결정 실행——사고 과정이 자동으로 아카이브됩니다. 나중에 검토할 때 "왜 이 접근 방식을 선택했는지"를 명확히 알 수 있습니다.

**개인 선호와 경험 축적**
Fact 추출을 통해 작업 습관, 자주 사용하는 도구, 과거의 함정이 장기 메로리에 자동으로 축적됩니다. Hermes를 사용할수록 당신을 더 깊이 이해하게 됩니다.

## 설치

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

`~/.hermes/config.yaml`에 `hermes-wiki` 추가:

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Hermes Agent 재시작으로 활성화. 플러그인은 config.yaml의 기존 LLM 설정(`model.default` / `model.provider`)을 자동 사용합니다.

## 작동 방식

**완전 자동 — 수동 작업 불필요.**

```
Hermes와 대화
  → 세션 종료 (닫기 / 주제 전환 / 리셋)
    → on_session_end 또는 on_session_reset 훅 발동 (밀리초, 비블로킹)
      → 훅이 메시지를 전달하지 않으면 state.db에서 읽기
        → 메시지를 SQLite에 큐잉 (날짜별 세그먼트)
          → 백그라운드 데몬 스레드 시작
            → 설정된 LLM 호출 (config.yaml에서)
              → 분석: 품질 점수 / 언어 / 주제 / 엔티티 / 의사결정 / facts
              → 구조화된 wiki 페이지를 SQLite에 기록 (quality >= 4)
              → 재사용 가능한 facts를 holographic memory에 추출 (확장 모드 시)
  → 1시간마다 배치 스캔 (훅이 놓친 것을 보완)
```

첫 실행 시 `~/.hermes/memory_store.db`에 SQLite 테이블(`wiki_pages`, `wiki_pending_queue`)을 자동 생성합니다.

## 기능

- **7개 언어 i18n**: en/zh/ja/ko/de/fr/es — LLM이 대화 언어를 감지하여 같은 언어로 wiki 페이지 생성
- **품질 점수**: 1-5 척도 (5=깊고 중요, 1=노이즈)
- **주제 분류 + 집계**：주제 자동 발견, 2시간마다 세션 페이지에서 주제 페이지 재구축
- **엔티티 추출**: 대화에서 주요 엔티티 식별
- **SQLite 3.31+ 호환**: Python 3.9+ 지원

## 문제 해결

**플러그인이 로드되지 않나요?**
- `~/.hermes/config.yaml`의 `plugins.enabled`에 `hermes-wiki`가 있는지 확인
- 디렉토리가 `~/.hermes/plugins/hermes_wiki/`인지 확인 (밑줄, 하이픈 아님)

## 사용법

### Wiki 페이지 검색

**독립 모드**:
```
사용자: nginx 토론에 대한 wiki 검색
Hermes: [wiki_search(query='nginx') 호출]
  → 일치하는 wiki 페이지 반환
```

**팁**: LLM이 항상 `wiki_search`를 우선하지 않을 수 있습니다. wiki 결과를 확실히 얻으려면 쿼리에서 명시적으로 "wiki"를 언급하세요:
```
사용자: wiki_search로 nginx 토론 검색
사용자: Wiki에서 오늘의 활동 검색
사용자: wiki에서 커스텀 엔드포인트 작업 검색
```

다중 단어 쿼리 지원 — 도구가 쿼리를 단어로 분리하여任意의 단어와 일치합니다:
```
사용자: wiki_search로 "wiki 플러그인 개발" 검색
  → "wiki" 또는 "플러그인" 또는 "개발"을 포함하는 페이지와 일치
```

## 라이선스

MIT
