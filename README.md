# hermes-wiki-plugin

> 🌐 [English](README.md) | [中文](docs/README.zh.md) | [日本語](docs/README.ja.md) | [한국어](docs/README.ko.md) | [Deutsch](docs/README.de.md) | [Français](docs/README.fr.md) | [Español](docs/README.es.md)

Karpathy LLM Wiki pattern for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — automatic session-to-wiki conversion with quality scoring, topic classification, entity extraction, cross-session topic aggregation, and 7-language i18n.

## Why This Exists

Hermes generates valuable conversations every day — debugging sessions, decision discussions, problem-solving, idea exploration. But this knowledge has three problems:

- **Knowledge sinks when the session ends.** Next time you face a similar problem, you remember "I dealt with something like this before" but can't recall the details. `session_search` can find raw conversations, but the results are noisy and fragmented.
- **No structured accumulation.** Conversations are linear chat logs, not documents organized by topic, decision, and outcome.
- **Cross-session knowledge can't connect.** The same topic discussed across different sessions, or different phases of the same project, can't be linked together.

## What It Does

The plugin automatically calls your LLM at the end of each session, distilling conversations into structured wiki pages. Topics discussed across multiple sessions are automatically aggregated into topic pages with cross-session insights.

- **Quality scoring** (1-5): Automatically filters noise, keeping only valuable sessions
- **Topic classification + entity extraction**: Automatically identifies "what this conversation was about"
- **Key decisions and problem resolution**: Extracts "what decisions were made, why, and how problems were solved"
- **Fact extraction**: Reusable knowledge (tool quirks, gotchas, workflow discoveries) is written to long-term memory, directly hittable by future searches
- **Topic aggregation**: Cross-session topics get LLM-integrated overview, timeline, entities, and evolution path
- **7-language support**: Wiki pages are generated in the same language as the conversation

## Use Cases

**Daily conversations build a knowledge base**
Whether asking technical questions, discussing work plans, or exploring new ideas, each conversation automatically generates a structured summary. Over time, the wiki becomes a knowledge base co-built by you and Hermes.

**Troubleshooting leaves traces**
Encountering errors, investigating root causes, finding solutions — this process automatically crystallizes into wiki pages. Next time a similar issue arises, searching the wiki is much faster than scrolling through chat history.

**Decision history is traceable**
Discussing approaches, comparing options, making decisions — the thinking process is automatically archived. When reviewing later, you can clearly see "why we chose this approach."

**Topics evolve across sessions**
When you work on the same topic across multiple sessions (e.g., a feature implementation, a debugging investigation), the plugin automatically creates a topic page that integrates insights from all related sessions — showing the evolution timeline, cross-session decisions, and patterns.

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
  → Session ends (close / switch topic / reset)
    → on_session_end or on_session_reset hook fires
      → Session messages read from state.db
        → LLM analyzes: quality / language / topics / entities / decisions / facts
          → Wiki page written to hermes_wiki_pages (quality >= 4)
          → Facts extracted to holographic memory (if active)
          → Dirty markers written for affected topics
  → 1-hour batch scan (catches anything the hooks missed)
  → 2-hour topic aggregation (processes dirty topics via LLM)
```

### Session Workflow (Wiki)

1. Session ends → hook fires → messages queued in SQLite
2. Background thread calls LLM with session messages
3. LLM returns: quality score, language, topics, entities, key decisions, full wiki content
4. Wiki page written to `hermes_wiki_pages` (quality >= 4)
5. Dirty markers written to `hermes_wiki_topic_dirty` for each topic slug

### Topic Workflow (Topic Aggregation)

1. Every 2 hours, `aggregate_topics()` reads dirty markers
2. For each dirty topic, fetches associated wiki pages' `full_content`
3. LLM integrates cross-session content: overview, decisions, patterns, evolution
4. Topic page written to `hermes_wiki_topics`
5. Dirty marker cleared on LLM success; re-marked on fallback (retry next cycle)

### Incremental Processing

Both workflows use incremental processing to avoid redundant LLM calls:

- **Wiki**: `hermes_wiki_session_state` tracks processed sessions; batch scan only processes new ones
- **Topic**: `hermes_wiki_topic_dirty` marks topics needing re-aggregation; only dirty topics are processed

## Trigger Conditions

| Scenario | Hook | Triggers wiki generation? |
|----------|------|--------------------------|
| Close window / disconnect / idle timeout | `on_session_end` | ✅ Immediate |
| Switch topic / `/new` | `on_session_reset` | ✅ Immediate |
| Existing session gains messages | batch scan | ✅ Within 1 hour |
| Cron job session | — | ❌ Skipped |
| Subagent session | — | ❌ Skipped |
| Fewer than 2 messages | — | ❌ Skipped |

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
- Tool is registered to the `memory` toolset

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

### Desktop GUI

The plugin provides a dual-panel sidebar in Hermes Desktop:

- **Left panel**: Topics (collapsible groups with session children) + All Pages (flat list)
- **Right panel**: Detail view with toolbar (back, export, edit, delete), metadata, and content
- **Batch selection**: Select mode with checkboxes across both Topics and All Pages
- **Topic detail**: Shows LLM-integrated overview, timeline, entities, and session links

### Checking Wiki Pages Directly

```bash
# List all wiki pages
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# List all topic pages
sqlite3 ~/.hermes/memory_store.db \
  "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# Check dirty topics pending aggregation
sqlite3 ~/.hermes/memory_store.db \
  "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## Architecture

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — entry point, hooks, 1h scan timer, topic module registration
│   ├── wiki_store.py        — SQLite: hermes_wiki_pages, session_state, pending_queue
│   ├── wiki_builder.py      — LLM session analysis and wiki page generation
│   ├── wiki_rpc.py          — wiki.* RPC methods (list, get, create, update, delete, stats)
│   ├── llm_client.py        — shared LLM HTTP client (provider resolution, Anthropic/OpenAI)
│   ├── rpc_utils.py         — shared JSON-RPC utilities (_err, parse_json_columns)
│   ├── topic/
│   │   ├── __init__.py      — topic module registration, 2h aggregation timer
│   │   ├── topic_store.py   — SQLite: hermes_wiki_topics, hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — LLM topic aggregation with dirty-marker incremental processing
│   │   └── topic_rpc.py     — topic.* RPC methods (list, get)
│   ├── prompts/
│   │   ├── wiki.md          — session → wiki prompt
│   │   └── topic.md         — topic aggregation prompt
│   └── plugin.yaml          — plugin metadata
├── desktop/
│   └── plugin.js            — Hermes Desktop GUI (dual-panel sidebar, DetailToolbar, batch selection)
├── docs/                    — multilingual READMEs (zh/ja/ko/de/fr/es)
├── README.md                — English documentation
└── install.sh               — installs backend + desktop + gateway RPC patch
```

### Data Flow

```
Session messages
  → wiki_builder (LLM) → hermes_wiki_pages (session type)
    → wiki_builder writes dirty markers → hermes_wiki_topic_dirty
      → topic_builder (LLM) reads wiki pages → hermes_wiki_topics
        → Desktop GUI reads via topic.list / topic.get RPC
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `hermes_wiki_pages` | Session wiki pages (page_type='session') |
| `hermes_wiki_session_state` | Tracks processed sessions (incremental wiki) |
| `hermes_wiki_pending_queue` | Queued sessions awaiting processing |
| `hermes_wiki_topics` | Topic aggregation pages (LLM-integrated) |
| `hermes_wiki_topic_dirty` | Dirty markers for incremental topic aggregation |

### RPC Methods

| Method | Description |
|--------|-------------|
| `wiki.list` | List session wiki pages |
| `wiki.get` | Get single wiki page |
| `wiki.create` | Create manual wiki page |
| `wiki.update` | Update wiki page |
| `wiki.delete` | Delete wiki page |
| `wiki.stats` | Wiki statistics |
| `wiki.batch_process` | Batch process pending sessions |
| `topic.list` | List topic pages |
| `topic.get` | Get single topic page with sessions |

## Features

- **7-Language i18n**: en/zh/ja/ko/de/fr/es — LLM detects session language and generates wiki pages in that language
- **Quality Scoring**: 1-5 scale (5=deep+important, 1=noise), low-quality sessions get minimal processing
- **Topic Aggregation**: Cross-session topics get LLM-integrated overview, decisions, patterns, and evolution timeline
- **Incremental Processing**: Dirty markers ensure only changed topics are re-aggregated; fallback retries on LLM failure
- **Entity Extraction**: Identifies key entities (people, tools, systems) from conversations
- **Fact Extraction**: Reusable knowledge written to holographic memory — searchable via `fact_store`
- **Dual Hook Triggers**: `on_session_end` + `on_session_reset` — near-instant wiki generation
- **Shared LLM Client**: Provider resolution, Anthropic/OpenAI format detection, .env loading
- **Desktop GUI**: Dual-panel sidebar with topic groups, batch selection, DetailToolbar, markdown rendering
- **Graceful Degradation**: Falls back to template when LLM unavailable; retries via dirty markers

## Troubleshooting

**Plugin not loading?**
- Check `~/.hermes/config.yaml` has `hermes-wiki` in `plugins.enabled`
- Check logs for `hermes-wiki: standalone mode` or `extension mode`
- Verify directory is `~/.hermes/plugins/hermes_wiki/` (underscore, not hyphen)

**No wiki pages generated?**
- Check LLM is configured: `model.default` and `model.provider` in config.yaml
- Check logs for `hermes-wiki: LLM failed` — indicates auth or network issue
- Minimum 2 messages per session required

**Topics not aggregating?**
- Check logs for `hermes-wiki: topic aggregation` messages
- Verify dirty markers exist: `sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- Topic aggregation runs every 2 hours; new topics may take up to 2 hours to appear

**wiki_search tool not available?**
- Only available in standalone mode (no holographic plugin)
- In extension mode, use `fact_store(action='search')` instead

## License

MIT
