# hermes-wiki-plugin

[Hermes Agent](https://github.com/NousResearch/hermes-agent)용 Karpathy LLM Wiki 패턴 플러그인 — 세션에서 wiki 페이지로 자동 변환, 품질 점수, 주제 분류, 엔티티 추출, 7개 언어 i18n 지원.

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

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
  → 세션 종료 (주제 전환 / 리셋 / 닫기)
    → on_session_end hook 발동 (밀리초, 비블로킹)
      → 메시지를 SQLite에 큐잉
        → 백그라운드 데몬 스레드 시작
          → LLM 호출 (config.yaml 설정 사용)
            → 분석: 품질 점수 / 언어 / 주제 / 엔티티 / 결정사항
            → 구조화된 wiki 페이지를 SQLite에 저장
            → facts를 fact_store에 추출
```

첫 실행 시 `~/.hermes/memory_store.db`에 SQLite 테이블(`wiki_pages`, `wiki_pending_queue`)을 자동 생성합니다.

## 기능

- **7개 언어 i18n**: en/zh/ja/ko/de/fr/es — LLM이 대화 언어를 감지하여 같은 언어로 wiki 페이지 생성
- **품질 점수**: 1-5 척도 (5=깊고 중요, 1=노이즈)
- **주제 분류**: 주제 자동 발견 및 집계 페이지 유지
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
