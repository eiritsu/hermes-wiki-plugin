# hermes-wiki-plugin

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Karpathy LLM Wiki pattern for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — automatic session-to-wiki conversion with quality scoring, topic classification, entity extraction, and 7-language i18n.

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

The installer places the backend in `~/.hermes/plugins/hermes_wiki/` and the Desktop GUI plugin in `~/.hermes/desktop-plugins/hermes-wiki/`.

Then edit `~/.hermes/config.yaml` — add `hermes-wiki` to the plugins list:

```yaml
plugins:
  enabled:
    - hermes-wiki
    # ... other plugins you already have
```

Restart Hermes Agent to activate.

The plugin uses whatever LLM you already configured in Hermes (`model.default` / `model.provider` in config.yaml). No extra LLM config needed.

## How It Works

**Fully automatic — no manual steps required.**

```
You chat with Hermes
  → Session ends (switch topic / reset / close)
    → on_session_end hook fires (milliseconds, non-blocking)
      → Session messages queued in SQLite
        → Background daemon thread starts
          → Calls your configured LLM (from config.yaml)
            → Analyzes: quality score / language / topics / entities / decisions
            → Writes structured wiki page to SQLite
            → Extracts facts into fact_store
```

The plugin auto-creates its SQLite tables (`hermes_wiki_pages`, `hermes_wiki_pending_queue`, and `hermes_wiki_session_state`) in `~/.hermes/memory_store.db` on first run. No manual database setup needed.

## Trigger Conditions

| Scenario | Triggers wiki generation? |
|----------|--------------------------|
| Normal conversation ends | ✅ Yes |
| Existing session gains messages | ✅ Rebuilt by the 5-minute incremental scan |
| Switch session | ✅ Yes |
| Reset session | ✅ Yes |
| Cron job session | ❌ Skipped |
| Subagent session | ❌ Skipped |
| Fewer than 2 messages | ❌ Skipped |

## Two Modes

The plugin auto-detects which mode to use at startup:

### Extension Mode (holographic memory plugin active)
- Shares holographic's SQLite connection
- `fact_store(action='search', query="...")` automatically includes wiki results alongside facts
- No extra tools needed — one search covers everything

### Standalone Mode (no holographic)
- Manages own SQLite connection
- Adds `wiki_search` tool for querying wiki pages
- Works independently of any other memory plugin

## Usage

### Searching Wiki Pages

**Extension mode** (holographic active):
```
You: What did we discuss about nginx configuration?
Hermes: [calls fact_store(action='search', query='nginx')]
  → Returns facts + wiki pages in one search
```

**Standalone mode**:
```
You: Search the wiki for nginx discussions
Hermes: [calls wiki_search(query='nginx')]
  → Returns matching wiki pages
```

### Checking Wiki Pages Directly

```bash
# List all wiki pages
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# Search by keyword
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, summary FROM hermes_wiki_pages WHERE title LIKE '%nginx%' OR summary LIKE '%nginx%'"

# Check pending queue
sqlite3 ~/.hermes/memory_store.db \
  "SELECT COUNT(*) FROM hermes_wiki_pending_queue WHERE status='pending'"
```

### Verifying the Plugin is Active

1. Check Hermes logs for: `hermes-wiki: standalone mode` or `hermes-wiki: extension mode`
2. After a few conversations, query: `sqlite3 ~/.hermes/memory_store.db "SELECT COUNT(*) FROM hermes_wiki_pages"`
3. Use the Desktop Wiki sidebar, `wiki_search` (standalone mode), or `fact_store(action='search')` (extension mode) to find wiki content

## Features

- **7-Language i18n**: en/zh/ja/ko/de/fr/es — LLM detects session language and generates wiki pages in that language
- **Quality Scoring**: 1-5 scale (5=deep+important, 1=noise), low-quality sessions get minimal processing
- **Topic Classification**: Auto-discovers topics, maintains topic aggregate pages with session timeline
- **Entity Extraction**: Identifies key entities (people, tools, systems) from conversations
- **Provider Resolution**: Uses Hermes's `PROVIDER_REGISTRY` — no hardcoded URLs
- **Graceful Degradation**: Falls back to default analysis when LLM unavailable
- **SQLite 3.31+ Compatible**: Works on Python 3.9+ (no RETURNING clause)

## Wiki Page Structure

Each wiki page includes:

```yaml
---
session_id: "20260718_143022_abc"
date: 2026-07-18
language: en
quality: 4
content_type: troubleshooting
topics: ["docker", "networking"]
entities: ["Docker Compose", "Nginx"]
keywords: ["container", "reverse proxy"]
result: "Resolved container networking issue and configured reverse proxy"
---

# Docker Networking Debug (2026-07-18)

## Background
Container couldn't reach external APIs due to DNS misconfiguration

## Key Decisions
- Used custom bridge network instead of default
- Added explicit DNS resolver in docker-compose.yml

## Problems & Solutions
- DNS timeout → switched to 8.8.8.8 as fallback resolver

## Result
Container networking resolved, reverse proxy configured
```

## Architecture

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — dual-mode entry point, hooks, 5-minute incremental scan
│   ├── wiki_store.py        — SQLite queue, retry, session state, and page storage
│   ├── wiki_builder.py      — LLM analysis and wiki page generation
│   ├── wiki_rpc.py          — Gateway RPC methods for the Desktop GUI
│   ├── plugin.yaml          — plugin metadata
│   └── prompts/default.md   — analysis prompt
├── desktop/plugin.js         — Hermes Desktop Wiki sidebar GUI
└── install.sh                — installs backend and Desktop components
```

## Troubleshooting

**Plugin not loading?**
- Check `~/.hermes/config.yaml` has `hermes-wiki` in `plugins.enabled`
- Check logs for `hermes-wiki: standalone mode` or `extension mode`
- Verify directory is `~/.hermes/plugins/hermes_wiki/` (underscore, not hyphen)

**No wiki pages generated?**
- Check LLM is configured: `model.default` and `model.provider` in config.yaml
- Check logs for `hermes-wiki: LLM failed` — indicates auth or network issue
- Minimum 2 messages per session required

**wiki_search tool not available?**
- Only available in standalone mode (no holographic plugin)
- In extension mode, use `fact_store(action='search')` instead

## License

MIT
