# hermes-wiki-plugin

Karpathy LLM Wiki Plugin für [Hermes Agent](https://github.com/NousResearch/hermes-agent) — automatische Session-zu-Wiki-Konvertierung mit Qualitätsbewertung, Topic-Klassifizierung, Entity-Extraktion und 7-Sprach-i18n.

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git ~/.hermes/plugins/hermes_wiki
```

In `~/.hermes/config.yaml` `hermes-wiki` zur Plugin-Liste hinzufügen:

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Hermes Agent neu starten. Das Plugin verwendet automatisch die vorhandene LLM-Konfiguration aus config.yaml (`model.default` / `model.provider`).

## Funktionsweise

**Vollautomatisch — kein manueller Eingriff erforderlich.**

```
Gespräch mit Hermes
  → Session endet (Themenwechsel / Reset / Schließen)
    → on_session_end Hook wird ausgelöst (Millisekunden, nicht blockierend)
      → Nachrichten werden in SQLite gequeued
        → Hintergrund-Thread startet
          → LLM-Aufruf (aus config.yaml)
            → Analyse: Qualität / Sprache / Topics / Entities / Entscheidungen
            → Strukturierte Wiki-Seite in SQLite geschrieben
            → Facts in fact_store extrahiert
```

## Funktionen

- **7-Sprach-i18n**: en/zh/ja/ko/de/fr/es — LLM erkennt die Gesprächssprache und generiert Wiki-Seiten in derselben Sprache
- **Qualitätsbewertung**: 1-5 Skala (5=tief+bedeutend, 1=Rauschen)
- **Topic-Klassifizierung**: Automatische Topic-Erkennung und aggregierte Seiten
- **Entity-Extraktion**: Identifizierung wichtiger Entitäten aus Gesprächen
- **SQLite 3.31+ kompatibel**: Python 3.9+ (kein RETURNING)

## Fehlerbehebung

**Plugin wird nicht geladen?**
- Prüfen Sie `~/.hermes/config.yaml` — `plugins.enabled` muss `hermes-wiki` enthalten
- Verzeichnis muss `~/.hermes/plugins/hermes_wiki/` sein (Unterstrich, nicht Bindestrich)

## Lizenz

MIT
