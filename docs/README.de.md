# hermes-wiki-plugin

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Karpathy LLM Wiki Plugin für [Hermes Agent](https://github.com/NousResearch/hermes-agent) — automatische Session-zu-Wiki-Konvertierung mit Qualitätsbewertung, Topic-Klassifizierung, Entity-Extraktion, Cross-Session-Topic-Aggregation und 7-Sprach-i18n.

## Warum dieses Plugin?

Hermes generiert täglich wertvolle Gespräche — Debugging-Sitzungen, Entscheidungsdiskussionen, Problemlösung, Ideenfindung. Aber dieses Wissen hat drei Probleme:

- **Wissen versinkt nach Sitzungsende.** Beim nächsten ähnlichen Problem erinnern Sie sich: „Das habe ich schon mal gemacht", aber die Details fehlen. `session_search` findet Rohgespräche, aber die Ergebnisse sind laut und fragmentiert.
- **Keine strukturierte Ablage.** Gespräche sind lineare Chat-Protokolle, keine nach Thema, Entscheidung und Ergebnis organisierten Dokumente.
- **Wissen lässt sich nicht über Sitzungen hinweg verknüpfen.** Dasselbe Thema in verschiedenen Sitzungen oder verschiedene Phasen desselben Projekts können nicht verbunden werden.

## Was es tut

Das Plugin ruft am Ende jeder Sitzung automatisch Ihr LLM auf und destilliert Gespräche zu strukturierten Wiki-Seiten. Themen, die über mehrere Sitzungen hinweg besprochen werden, werden automatisch in Topic-Seiten mit Cross-Session-Insights aggregiert.

- **Qualitätsbewertung** (1-5): Filtert automatisch Rauschen und behält nur wertvolle Sitzungen
- **Topic-Klassifizierung + Entity-Extraktion**: Erkennt automatisch, „worum es in diesem Gespräch ging"
- **Wichtige Entscheidungen und Problemlösungen**: Extrahiert „welche Entscheidungen getroffen wurden, warum und wie Probleme gelöst wurden"
- **Fact-Extraktion**: Wiederverwendbares Wissen (Tool-Eigenheiten, Stolperfallen, Workflow-Entdeckungen) wird ins Langzeitgedächtnis geschrieben und bei zukünftigen Suchen direkt gefunden
- **Topic-Aggregation**: Cross-Session-Themen erhalten LLM-integrierte Übersicht, Timeline, Entities und Entwicklungsverlauf
- **7-Sprachen-Unterstützung**: Wiki-Seiten werden in derselben Sprache wie das Gespräch generiert

## Anwendungsfälle

**Tägliche Gespräche bauen eine Wissensbasis auf**
Ob technische Fragen, Besprechung von Arbeitsplänen oder Erkundung neuer Ideen — nach jedem Gespräch wird automatisch eine strukturierte Zusammenfassung erstellt. Mit der Zeit wird das Wiki zur gemeinsamen Wissensbasis von Ihnen und Hermes.

**Fehlersuche hinterlässt Spuren**
Fehler finden, Ursachen untersuchen, Lösungen entdecken — dieser Prozess kristallisiert sich automatisch zu Wiki-Seiten. Beim nächsten ähnlichen Problem ist die Wiki-Suche viel schneller als das Scrollen durch Chat-Verläufe.

**Entscheidungshistorie ist nachvollziehbar**
Ansätze diskutieren, Optionen vergleichen, Entscheidungen treffen — der Denkprozess wird automatisch archiviert. Bei der späteren Überprüfung sieht man klar: „Warum haben wir diesen Ansatz gewählt?"

**Themen entwickeln sich über Sitzungen hinweg**
Wenn Sie über mehrere Sitzungen am selben Thema arbeiten (z. B. Feature-Implementierung, Debugging-Untersuchung), erstellt das Plugin automatisch eine Topic-Seite, die Insights aller zugehörigen Sitzungen integriert — mit Entwicklungs-Timeline, Cross-Session-Entscheidungen und Mustern.

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

Das Installationsprogramm platziert das Backend in `~/.hermes/plugins/hermes_wiki/` und das Desktop-GUI-Plugin in `~/.hermes/desktop-plugins/hermes-wiki/`.

Dann bearbeiten Sie `~/.hermes/config.yaml` — fügen Sie `hermes-wiki` zur Plugin-Liste hinzu:

```yaml
plugins:
  enabled:
    - hermes-wiki
    # ... weitere Plugins, die Sie bereits haben
```

Starten Sie Hermes Agent neu, um zu aktivieren.

Das Plugin verwendet automatisch die vorhandene LLM-Konfiguration aus config.yaml (`model.default` / `model.provider`). Keine zusätzliche LLM-Konfiguration erforderlich.

## Funktionsweise

**Vollautomatisch — kein manueller Eingriff erforderlich.**

```
Gespräch mit Hermes
  → Sitzung endet (Themenwechsel / Reset / Schließen)
    → on_session_end oder on_session_reset Hook wird ausgelöst
      → Sitzungsnachrichten aus state.db gelesen
        → LLM-Analyse: Qualität / Sprache / Topics / Entities / Entscheidungen / Facts
          → Wiki-Seite in hermes_wiki_pages geschrieben (quality >= 4)
          → Facts in holographic memory extrahiert (falls aktiv)
          → Dirty-Marker für betroffene Topics geschrieben
  → 1-Stunden-Batch-Scan (fängt ab, was die Hooks verpasst haben)
  → 2-Stunden-Topic-Aggregation (verarbeitet Dirty-Topics per LLM)
```

### Sitzungs-Workflow (Wiki)

1. Sitzung endet → Hook wird ausgelöst → Nachrichten in SQLite gequeued
2. Hintergrund-Thread sendet Sitzungsnachrichten an LLM
3. LLM liefert: Qualitätsscore, Sprache, Topics, Entities, Schlüsselentscheidungen, Wiki-Inhalt
4. Wiki-Seite in `hermes_wiki_pages` geschrieben (quality >= 4)
5. Dirty-Marker in `hermes_wiki_topic_dirty` für jeden Topic-Slug geschrieben

### Topic-Workflow (Topic-Aggregation)

1. Alle 2 Stunden liest `aggregate_topics()` die Dirty-Marker
2. Für jedes Dirty-Topic werden die zugehörigen Wiki-Seiten (`full_content`) abgerufen
3. LLM integriert Cross-Session-Inhalte: Übersicht, Entscheidungen, Muster, Entwicklung
4. Topic-Seite in `hermes_wiki_topics` geschrieben
5. Dirty-Marker bei LLM-Erfolg gelöscht; bei Fallback erneut markiert (nächster Zyklus)

### Inkrementelle Verarbeitung

Beide Workflows verwenden inkrementelle Verarbeitung, um redundante LLM-Aufrufe zu vermeiden:

- **Wiki**: `hermes_wiki_session_state` verarbeitete Sitzungen; Batch-Scan verarbeitet nur neue
- **Topic**: `hermes_wiki_topic_dirty` markiert Topics, die neu aggregiert werden müssen; nur Dirty-Topics werden verarbeitet

## Trigger-Bedingungen

| Szenario | Hook | Wiki-Generierung? |
|----------|------|--------------------------|
| Fenster schließen / Verbindung trennen / Idle-Timeout | `on_session_end` | ✅ Sofort |
| Topic wechseln / `/new` | `on_session_reset` | ✅ Sofort |
| Bestehende Sitzung erhält Nachrichten | Batch-Scan | ✅ Innerhalb 1 Stunde |
| Cron-Job-Sitzung | — | ❌ Übersprungen |
| Subagent-Sitzung | — | ❌ Übersprungen |
| Weniger als 2 Nachrichten | — | ❌ Übersprungen |

## Zwei Modi

Das Plugin erkennt beim Start automatisch den verwendeten Modus:

### Extension-Modus (holographic memory Plugin aktiv)
- Teilt die SQLite-Verbindung von holographic
- `fact_store(action='search', query="...")` enthält automatisch Wiki-Ergebnisse neben Facts
- Keine zusätzlichen Tools nötig — eine Suche deckt alles ab

### Standalone-Modus (kein holographic)
- Verwaltet eigene SQLite-Verbindung
- Fügt `wiki_search`-Tool für Wiki-Abfragen hinzu
- Arbeitet unabhängig von anderen Memory-Plugins
- Tool ist im `memory`-Toolset registriert

## Verwendung

### Wiki-Seiten durchsuchen

**Extension-Modus** (holographic aktiv):
```
Du: Was haben wir über die nginx-Konfiguration besprochen?
Hermes: [ruft fact_store(action='search', query='nginx') auf]
  → Liefert Facts + Wiki-Seiten in einer Suche
```

**Standalone-Modus**:
```
Du: Suche im Wiki nach nginx-Diskussionen
Hermes: [ruft wiki_search(query='nginx') auf]
  → Liefert passende Wiki-Seiten
```

### Desktop-GUI

Das Plugin bietet eine Zwei-Panel-Sidebar in Hermes Desktop:

- **Linkes Panel**: Topics (aufklappbare Gruppen mit Sitzungs-Kindern) + Alle Seiten (flache Liste)
- **Rechtes Panel**: Detailansicht mit Toolbar (Zurück, Exportieren, Bearbeiten, Löschen), Metadaten und Inhalt
- **Stapelauswahl**: Auswahlmodus mit Checkboxen für Topics und Alle Seiten
- **Topic-Detail**: LLM-integrierte Übersicht, Timeline, Entities und Sitzungslinks

### Wiki-Seiten direkt prüfen

```bash
# Alle Wiki-Seiten auflisten
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# Alle Topic-Seiten auflisten
sqlite3 ~/.hermes/memory_store.db \
  "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# Dirty-Topics prüfen, die auf Aggregation warten
sqlite3 ~/.hermes/memory_store.db \
  "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## Architektur

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — Einstiegspunkt, Hooks, 1h-Scan-Timer, Topic-Modul-Registrierung
│   ├── wiki_store.py        — SQLite: hermes_wiki_pages, session_state, pending_queue
│   ├── wiki_builder.py      — LLM-Sitzungsanalyse und Wiki-Seiten-Generierung
│   ├── wiki_rpc.py          — wiki.* RPC-Methoden (list, get, create, update, delete, stats)
│   ├── llm_client.py        — Gemeinsamer LLM-HTTP-Client (Provider-Auflösung, Anthropic/OpenAI)
│   ├── rpc_utils.py         — Gemeinsame JSON-RPC-Utilities (_err, parse_json_columns)
│   ├── topic/
│   │   ├── __init__.py      — Topic-Modul-Registrierung, 2h-Aggregations-Timer
│   │   ├── topic_store.py   — SQLite: hermes_wiki_topics, hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — LLM-Topic-Aggregation mit Dirty-Marker-Inkrementalverarbeitung
│   │   └── topic_rpc.py     — topic.* RPC-Methoden (list, get)
│   ├── prompts/
│   │   ├── default.md       — Sitzungsanalyse-Prompt
│   │   └── topic.md         — Topic-Aggregations-Prompt
│   └── plugin.yaml          — Plugin-Metadaten
├── desktop/
│   └── plugin.js            — Hermes Desktop GUI (Zwei-Panel-Sidebar, DetailToolbar, Stapelauswahl)
├── docs/                    — Mehrsprachige READMEs (zh/ja/ko/de/fr/es)
├── README.md                — Englische Dokumentation
└── install.sh               — Installiert Backend + Desktop + Gateway-RPC-Patch
```

### Datenfluss

```
Sitzungsnachrichten
  → wiki_builder (LLM) → hermes_wiki_pages (Sitzungstyp)
    → wiki_builder schreibt Dirty-Marker → hermes_wiki_topic_dirty
      → topic_builder (LLM) liest Wiki-Seiten → hermes_wiki_topics
        → Desktop GUI liest via topic.list / topic.get RPC
```

### Datenbanktabellen

| Tabelle | Zweck |
|-------|---------|
| `hermes_wiki_pages` | Sitzungs-Wiki-Seiten (page_type='session') |
| `hermes_wiki_session_state` | Verarbeitete Sitzungen (inkrementelles Wiki) |
| `hermes_wiki_pending_queue` | Warteschlange zu verarbeitender Sitzungen |
| `hermes_wiki_topics` | Topic-Aggregationsseiten (LLM-integriert) |
| `hermes_wiki_topic_dirty` | Dirty-Marker für inkrementelle Topic-Aggregation |

### RPC-Methoden

| Methode | Beschreibung |
|--------|-------------|
| `wiki.list` | Sitzungs-Wiki-Seiten auflisten |
| `wiki.get` | Einzelne Wiki-Seite abrufen |
| `wiki.create` | Manuelle Wiki-Seite erstellen |
| `wiki.update` | Wiki-Seite aktualisieren |
| `wiki.delete` | Wiki-Seite löschen |
| `wiki.stats` | Wiki-Statistiken |
| `wiki.batch_process` | Ausstehende Sitzungen stapelweise verarbeiten |
| `topic.list` | Topic-Seiten auflisten |
| `topic.get` | Einzelne Topic-Seite mit Sitzungen abrufen |

## Funktionen

- **7-Sprach-i18n**: en/zh/ja/ko/de/fr/es — LLM erkennt die Gesprächssprache und generiert Wiki-Seiten in derselben Sprache
- **Qualitätsbewertung**: 1-5 Skala (5=tief+bedeutend, 1=Rauschen), niedrigwertige Sitzungen werden minimal verarbeitet
- **Topic-Aggregation**: Cross-Session-Themen erhalten LLM-integrierte Übersicht, Entscheidungen, Muster und Entwicklungs-Timeline
- **Inkrementelle Verarbeitung**: Dirty-Marker stellen sicher, dass nur geänderte Topics neu aggregiert werden; Fallback bei LLM-Fehlern
- **Entity-Extraktion**: Identifiziert Schlüssel-Entities (Personen, Tools, Systeme) aus Gesprächen
- **Fact-Extraktion**: Wiederverwendbares Wissen wird in holographic memory geschrieben — über `fact_store` durchsuchbar
- **Dual-Hook-Trigger**: `on_session_end` + `on_session_reset` — nahezu sofortige Wiki-Generierung
- **Gemeinsamer LLM-Client**: Provider-Auflösung, Anthropic/OpenAI-Format-Erkennung, .env-Laden
- **Desktop-GUI**: Zwei-Panel-Sidebar mit Topic-Gruppen, Stapelauswahl, DetailToolbar, Markdown-Rendering
- **Graceful Degradation**: Fallback auf Template bei nicht verfügbarem LLM; Wiederholung über Dirty-Marker

## Fehlerbehebung

**Plugin wird nicht geladen?**
- Prüfen Sie `~/.hermes/config.yaml` — `plugins.enabled` muss `hermes-wiki` enthalten
- Prüfen Sie die Logs auf `hermes-wiki: standalone mode` oder `extension mode`
- Verzeichnis muss `~/.hermes/plugins/hermes_wiki/` sein (Unterstrich, nicht Bindestrich)

**Keine Wiki-Seiten werden generiert?**
- Prüfen Sie, ob LLM konfiguriert ist: `model.default` und `model.provider` in config.yaml
- Prüfen Sie die Logs auf `hermes-wiki: LLM failed` — zeigt Authentifizierungs- oder Netzwerkproblem
- Mindestens 2 Nachrichten pro Sitzung erforderlich

**Topics werden nicht aggregiert?**
- Prüfen Sie die Logs auf `hermes-wiki: topic aggregation`-Meldungen
- Prüfen Sie, ob Dirty-Marker existieren: `sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- Topic-Aggregation läuft alle 2 Stunden; neue Topics können bis zu 2 Stunden benötigen

**wiki_search-Tool nicht verfügbar?**
- Nur im Standalone-Modus verfügbar (kein holographic Plugin)
- Im Extension-Modus verwenden Sie stattdessen `fact_store(action='search')`

## Lizenz

MIT
