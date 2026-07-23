# hermes-wiki-plugin

Karpathy LLM Wiki Plugin für [Hermes Agent](https://github.com/NousResearch/hermes-agent) — automatische Session-zu-Wiki-Konvertierung mit Qualitätsbewertung, Topic-Klassifizierung, Entity-Extraktion und 7-Sprach-i18n.

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## Warum dieses Plugin?

Hermes generiert täglich wertvolle Gespräche — Debugging-Sitzungen, Entscheidungsdiskussionen, Problemlösung, Ideenfindung. Aber dieses Wissen hat drei Probleme:

- **Wissen versinkt nach Sitzungsende.** Beim nächsten ähnlichen Problem erinnern Sie sich: „Das habe ich schon mal gemacht", aber die Details fehlen. `session_search` findet Rohgespräche, aber die Ergebnisse sind laut und fragmentiert.
- **Keine strukturierte Ablage.** Gespräche sind lineare Chat-Protokolle, keine nach Thema, Entscheidung und Ergebnis organisierten Dokumente.
- **Wissen lässt sich nicht über Sitzungen hinweg verknüpfen.** Dasselbe Thema in verschiedenen Sitzungen oder verschiedene Phasen desselben Projekts können nicht verbunden werden.

## Was es tut

Das Plugin ruft am Ende jeder Sitzung automatisch Ihr LLM auf und destilliert Gespräche zu strukturierten Wiki-Seiten:

- **Qualitätsbewertung** (1-5): Filtert automatisch Rauschen und behält nur wertvolle Sitzungen
- **Themen-Klassifizierung + Entity-Extraktion**: Erkennt automatisch, „worum es in diesem Gespräch ging"
- **Wichtige Entscheidungen und Problemlösungen**: Extrahiert „welche Entscheidungen getroffen wurden, warum und wie Probleme gelöst wurden"
- **Fact-Extraktion**: Wiederverwendbares Wissen (Tool-Eigenheiten, Stolperfallen, Workflow-Entdeckungen) wird ins Langzeitgedächtnis geschrieben und bei zukünftigen Suchen direkt gefunden
- **7-Sprachen-Unterstützung**: Wiki-Seiten werden in derselben Sprache wie das Gespräch generiert

## Anwendungsfälle

**Tägliche Gespräche bauen eine Wissensbasis auf**
Ob technische Fragen, Besprechung von Arbeitsplänen oder Erkundung neuer Ideen — nach jedem Gespräch wird automatisch eine strukturierte Zusammenfassung erstellt. Mit der Zeit wird das Wiki zur gemeinsamen Wissensbasis von Ihnen und Hermes.

**Fehlersuche hinterlässt Spuren**
Fehler finden, Ursachen untersuchen, Lösungen entdecken — dieser Prozess kristallisiert sich automatisch zu Wiki-Seiten. Beim nächsten ähnlichen Problem ist die Wiki-Suche viel schneller als das Scrollen durch Chat-Verläufe.

**Entscheidungshistorie ist nachvollziehbar**
Ansätze diskutieren, Optionen vergleichen, Entscheidungen treffen — der Denkprozess wird automatisch archiviert. Bei der späteren Überprüfung sieht man klar: „Warum haben wir diesen Ansatz gewählt?"

**Persönliche Vorlieben und Erfahrungen sammeln sich**
Durch Fact-Extraktion bauen sich Arbeitsgewohnheiten, häufig genutzte Tools und vergangene Stolperfallen automatisch im Langzeitgedächtnis auf. Je mehr Sie Hermes nutzen, desto besser versteht er Sie.

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
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
- **Topic-Klassifizierung + Aggregation**：Automatische Topic-Erkennung, Neuaufbau der Topic-Seiten alle 2 Stunden aus Sitzungsseiten
- **Entity-Extraktion**: Identifizierung wichtiger Entitäten aus Gesprächen
- **SQLite 3.31+ kompatibel**: Python 3.9+ (kein RETURNING)

## Fehlerbehebung

**Plugin wird nicht geladen?**
- Prüfen Sie `~/.hermes/config.yaml` — `plugins.enabled` muss `hermes-wiki` enthalten
- Verzeichnis muss `~/.hermes/plugins/hermes_wiki/` sein (Unterstrich, nicht Bindestrich)

## Verwendung

### Wiki-Seiten durchsuchen

**Standalone-Modus**:
```
Du: Suche nach nginx-Diskussionen im Wiki
Hermes: [ruft wiki_search(query='nginx') auf]
  → Gibt passende Wiki-Seiten zurück
```

**Tipp**: Das LLM bevorzugt nicht immer `wiki_search`. Um Wiki-Ergebnisse sicherzustellen, erwähne explizit "wiki" in deiner Anfrage:
```
Du: Verwende wiki_search um nach nginx-Diskussionen zu suchen
Du: Wiki-Suche nach heutigen Aktivitäten
Du: Suche im Wiki nach Custom-Endpoint-Arbeit
```

Mehrwort-Suchanfragen werden unterstützt — das Tool teilt Ihre Anfrage in Wörter auf und stimmt mit einem beliebigen überein:
```
Du: wiki_search für "wiki plugin Entwicklung"
  → Findet Seiten mit "wiki" ODER "plugin" ODER "Entwicklung"
```

## Lizenz

MIT
