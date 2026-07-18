# hermes-wiki-plugin

Karpathy LLM Wiki pattern for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — automatic session-to-wiki conversion with quality scoring, topic classification, entity extraction, and 7-language i18n.

## How It Works

```
Session ends → Queue (non-blocking) → Background thread → LLM analysis → Wiki pages + facts
```

Wiki pages are stored in SQLite (`memory_store.db`) with structured metadata: quality score, topics, entities, language, content type.

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git ~/.hermes/plugins/hermes_wiki
```

Then add to `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Restart Hermes to activate.

## Two Modes

### Extension Mode (holographic active)
- Shares holographic's SQLite connection
- `fact_store(action='search')` automatically includes wiki results
- No extra tools needed

### Standalone Mode (no holographic)
- Manages own SQLite connection
- Adds `wiki_search` tool for querying wiki pages
- Works independently

The plugin auto-detects which mode to use at startup.

## Features

- **7-Language i18n**: en/zh/ja/ko/de/fr/es — LLM detects session language and responds accordingly
- **Quality Scoring**: 1-5 scale, low-quality sessions get minimal processing
- **Topic Classification**: Auto-discovers topics, maintains topic aggregate pages
- **Entity Extraction**: Identifies key entities from conversations
- **Provider Resolution**: Uses `PROVIDER_REGISTRY` — no hardcoded URLs
- **Graceful Degradation**: Falls back to default analysis when LLM unavailable
- **SQLite 3.31+ Compatible**: Works on Python 3.9+ (no RETURNING clause)

## Architecture

```
hermes_wiki/
├── __init__.py      — Dual-mode entry point, hook registration
├── wiki_store.py    — SQLite tables + queue management
├── wiki_builder.py  — LLM analysis + wiki page generation
└── plugin.yaml      — Plugin metadata
```

## License

MIT
