# hermes-wiki-plugin

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Plugin Karpathy LLM Wiki pour [Hermes Agent](https://github.com/NousResearch/hermes-agent) — conversion automatique des sessions en pages wiki avec notation de qualité, classification des sujets, extraction d'entités, agrégation inter-sessions et i18n en 7 langues.

## Pourquoi ce plugin ?

Hermes génère chaque jour des conversations précieuses — sessions de débogage, discussions de décisions, résolution de problèmes, exploration d'idées. Mais ces connaissances ont trois problèmes :

- **Le savoir disparaît à la fin de la session.** La prochaine fois que vous rencontrez un problème similaire, vous vous souvenez « j'ai déjà traité quelque chose comme ça » mais les détails manquent. `session_search` peut trouver les conversations brutes, mais les résultats sont bruités et fragmentés.
- **Pas d'accumulation structurée.** Les conversations sont des journaux de chat linéaires, pas des documents organisés par sujet, décision et résultat.
- **Le savoir ne peut pas être lié entre les sessions.** Un même sujet discuté dans différentes sessions, ou différentes phases d'un même projet, ne peuvent pas être reliés.

## Ce qu'il fait

Le plugin appelle automatiquement votre LLM à la fin de chaque session, distillant les conversations en pages wiki structurées. Les sujets discutés dans plusieurs sessions sont automatiquement agrégés en pages de sujets avec des insights inter-sessions.

- **Notation de qualité** (1-5) : Filtre automatiquement le bruit, ne gardant que les sessions valorables
- **Classification des sujets + extraction d'entités** : Identifie automatiquement « de quoi parlait cette conversation »
- **Décisions clés et résolution de problèmes** : Extrait « quelles décisions ont été prises, pourquoi et comment les problèmes ont été résolus »
- **Extraction de facts** : Les connaissances réutilisables (particularités des outils, pièges, découvertes de workflows) sont écrites en mémoire à long terme, directement trouvables lors des futures recherches
- **Agrégation de sujets** : Les sujets inter-sessions obtiennent une vue d'ensemble intégrée par LLM, une timeline, des entités et un chemin d'évolution
- **Support 7 langues** : Les pages wiki sont générées dans la même langue que la conversation

## Cas d'usage

**Les conversations quotidiennes construissent une base de connaissances**
Que ce soit des questions techniques, des discussions de plans de travail ou l'exploration de nouvelles idées, chaque conversation génère automatiquement un résumé structuré. Au fil du temps, le wiki devient une base de connaissances co-construite par vous et Hermes.

**Le dépannage laisse des traces**
Rencontrer des erreurs, enquêter sur les causes, trouver des solutions — ce processus se cristallise automatiquement en pages wiki. La prochaine fois qu'un problème similaire survient, chercher dans le wiki est bien plus rapide que parcourir l'historique des discussions.

**L'historique des décisions est traçable**
Discuter des approches, comparer les options, prendre des décisions — le processus de réflexion est automatiquement archivé. Lors d'une révision ultérieure, on voit clairement « pourquoi nous avons choisi cette approche ».

**Les sujets évoluent entre les sessions**
Quand vous travaillez sur le même sujet dans plusieurs sessions (ex. implémentation d'une fonctionnalité, investigation de débogage), le plugin crée automatiquement une page de sujet qui intègre les insights de toutes les sessions associées — montrant la timeline d'évolution, les décisions inter-sessions et les patterns.

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

L'installeur place le backend dans `~/.hermes/plugins/hermes_wiki/` et le plugin GUI Desktop dans `~/.hermes/desktop-plugins/hermes-wiki/`.

Puis éditez `~/.hermes/config.yaml` — ajoutez `hermes-wiki` à la liste des plugins :

```yaml
plugins:
  enabled:
    - hermes-wiki
    # ... autres plugins que vous avez déjà
```

Redémarrez Hermes Agent pour activer.

Le plugin utilise automatiquement la configuration LLM existante (`model.default` / `model.provider` dans config.yaml). Aucune configuration LLM supplémentaire requise.

## Fonctionnement

**Entièrement automatique — aucune intervention manuelle requise.**

```
Conversation avec Hermes
  → Session terminée (changement de sujet / réinitialisation / fermeture)
    → Hook on_session_end ou on_session_reset déclenché
      → Messages de session lus depuis state.db
        → Analyse LLM : qualité / langue / sujets / entités / décisions / facts
          → Page wiki écrite dans hermes_wiki_pages (quality >= 4)
          → Facts extraits dans holographic memory (si actif)
          → Dirty markers écrits pour les sujets affectés
  → Scan batch toutes les heures (capture ce que les hooks ont manqué)
  → Agrégation de sujets toutes les 2 heures (traite les sujets dirty via LLM)
```

### Workflow de session (Wiki)

1. Session terminée → hook déclenché → messages mis en file dans SQLite
2. Le thread d'arrière-plan envoie les messages de session au LLM
3. Le LLM retourne : score de qualité, langue, sujets, entités, décisions clés, contenu wiki complet
4. Page wiki écrite dans `hermes_wiki_pages` (quality >= 4)
5. Dirty markers écrits dans `hermes_wiki_topic_dirty` pour chaque slug de sujet

### Workflow de sujet (Agrégation)

1. Toutes les 2 heures, `aggregate_topics()` lit les dirty markers
2. Pour chaque sujet dirty, récupère le `full_content` des pages wiki associées
3. Le LLM intègre le contenu inter-sessions : vue d'ensemble, décisions, patterns, évolution
4. Page de sujet écrite dans `hermes_wiki_topics`
5. Dirty marker supprimé en cas de succès LLM ; re-marqué en cas de fallback (réessai au prochain cycle)

### Traitement incrémental

Les deux workflows utilisent le traitement incrémental pour éviter les appels LLM redondants :

- **Wiki** : `hermes_wiki_session_state` suit les sessions traitées ; le scan batch ne traite que les nouvelles
- **Sujet** : `hermes_wiki_topic_dirty` marque les sujets nécessitant une ré-agrégation ; seuls les sujets dirty sont traités

## Conditions de déclenchement

| Scénario | Hook | Déclenche la génération wiki ? |
|----------|------|--------------------------|
| Fermeture de fenêtre / déconnexion / timeout d'inactivité | `on_session_end` | ✅ Immédiat |
| Changement de sujet / `/new` | `on_session_reset` | ✅ Immédiat |
| Session existante reçoit des messages | scan batch | ✅ Dans l'heure |
| Session de cron job | — | ❌ Ignoré |
| Session de subagent | — | ❌ Ignoré |
| Moins de 2 messages | — | ❌ Ignoré |

## Deux modes

Le plugin détecte automatiquement le mode à utiliser au démarrage :

### Mode Extension (plugin holographic memory actif)
- Partage la connexion SQLite de holographic
- `fact_store(action='search', query="...")` inclut automatiquement les résultats wiki avec les facts
- Aucun outil supplémentaire nécessaire — une seule recherche couvre tout

### Mode Standalone (pas de holographic)
- Gère sa propre connexion SQLite
- Ajoute l'outil `wiki_search` pour les requêtes wiki
- Fonctionne indépendamment de tout autre plugin mémoire
- L'outil est enregistré dans le toolset `memory`

## Utilisation

### Recherche de pages Wiki

**Mode Extension** (holographic actif) :
```
Toi : Qu'est-ce qu'on a dit sur la configuration nginx ?
Hermes : [appelle fact_store(action='search', query='nginx')]
  → Retourne facts + pages wiki en une seule recherche
```

**Mode Standalone** :
```
Toi : Recherche les discussions nginx dans le wiki
Hermes : [appelle wiki_search(query='nginx')]
  → Retourne les pages wiki correspondantes
```

### GUI Desktop

Le plugin fournit une sidebar à double panneau dans Hermes Desktop :

- **Panneau gauche** : Sujets (groupes réductibles avec enfants sessions) + Toutes les pages (liste plate)
- **Panneau droit** : Vue détaillée avec barre d'outils (retour, export, édition, suppression), métadonnées et contenu
- **Sélection par lot** : Mode sélection avec cases à cocher pour Sujets et Toutes les pages
- **Détail du sujet** : Vue d'ensemble intégrée par LLM, timeline, entités et liens de sessions

### Vérifier les pages Wiki directement

```bash
# Lister toutes les pages wiki
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# Lister toutes les pages de sujets
sqlite3 ~/.hermes/memory_store.db \
  "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# Vérifier les sujets dirty en attente d'agrégation
sqlite3 ~/.hermes/memory_store.db \
  "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## Architecture

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — point d'entrée, hooks, timer scan 1h, enregistrement module sujets
│   ├── wiki_store.py        — SQLite : hermes_wiki_pages, session_state, pending_queue
│   ├── wiki_builder.py      — Analyse LLM de session et génération de pages wiki
│   ├── wiki_rpc.py          — Méthodes RPC wiki.* (list, get, create, update, delete, stats)
│   ├── llm_client.py        — Client HTTP LLM partagé (résolution provider, Anthropic/OpenAI)
│   ├── rpc_utils.py         — Utilitaires JSON-RPC partagés (_err, parse_json_columns)
│   ├── topic/
│   │   ├── __init__.py      — Enregistrement module sujets, timer agrégation 2h
│   │   ├── topic_store.py   — SQLite : hermes_wiki_topics, hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — Agrégation LLM de sujets avec traitement incrémental dirty-marker
│   │   └── topic_rpc.py     — Méthodes RPC topic.* (list, get)
│   ├── prompts/
│   │   ├── default.md       — Prompt d'analyse de session
│   │   └── topic.md         — Prompt d'agrégation de sujets
│   └── plugin.yaml          — Métadonnées du plugin
├── desktop/
│   └── plugin.js            — GUI Hermes Desktop (sidebar double panneau, DetailToolbar, sélection par lot)
├── docs/                    — READMEs multilingues (zh/ja/ko/de/fr/es)
├── README.md                — Documentation anglaise
└── install.sh               — Installe backend + desktop + patch gateway RPC
```

### Flux de données

```
Messages de session
  → wiki_builder (LLM) → hermes_wiki_pages (type session)
    → wiki_builder écrit les dirty markers → hermes_wiki_topic_dirty
      → topic_builder (LLM) lit les pages wiki → hermes_wiki_topics
        → GUI Desktop lit via topic.list / topic.get RPC
```

### Tables de base de données

| Table | Usage |
|-------|---------|
| `hermes_wiki_pages` | Pages wiki de sessions (page_type='session') |
| `hermes_wiki_session_state` | Suivi des sessions traitées (wiki incrémental) |
| `hermes_wiki_pending_queue` | File d'attente de sessions à traiter |
| `hermes_wiki_topics` | Pages d'agrégation de sujets (LLM intégré) |
| `hermes_wiki_topic_dirty` | Dirty markers pour l'agrégation incrémentale de sujets |

### Méthodes RPC

| Méthode | Description |
|--------|-------------|
| `wiki.list` | Lister les pages wiki de sessions |
| `wiki.get` | Obtenir une page wiki unique |
| `wiki.create` | Créer une page wiki manuelle |
| `wiki.update` | Mettre à jour une page wiki |
| `wiki.delete` | Supprimer une page wiki |
| `wiki.stats` | Statistiques wiki |
| `wiki.batch_process` | Traiter par lot les sessions en attente |
| `topic.list` | Lister les pages de sujets |
| `topic.get` | Obtenir une page de sujet unique avec sessions |

## Fonctionnalités

- **i18n 7 langues** : en/zh/ja/ko/de/fr/es — le LLM détecte la langue de la conversation et génère les pages wiki dans cette langue
- **Notation de qualité** : échelle 1-5 (5=profond+important, 1=bruit), les sessions de faible qualité sont traitées au minimum
- **Agrégation de sujets** : les sujets inter-sessions obtiennent une vue d'ensemble intégrée par LLM, décisions, patterns et timeline d'évolution
- **Traitement incrémental** : les dirty markers garantissent que seuls les sujets modifiés sont ré-agrégés ; fallback en cas d'échec LLM
- **Extraction d'entités** : identifie les entités clés (personnes, outils, systèmes) des conversations
- **Extraction de facts** : connaissances réutilisables écrites dans holographic memory — cherchable via `fact_store`
- **Double hook de déclenchement** : `on_session_end` + `on_session_reset` — génération wiki quasi instantanée
- **Client LLM partagé** : résolution provider, détection de format Anthropic/OpenAI, chargement .env
- **GUI Desktop** : sidebar double panneau avec groupes de sujets, sélection par lot, DetailToolbar, rendu markdown
- **Dégradation gracieuse** : fallback sur template quand le LLM est indisponible ; réessai via dirty markers

## Dépannage

**Plugin non chargé ?**
- Vérifiez que `~/.hermes/config.yaml` contient `hermes-wiki` dans `plugins.enabled`
- Vérifiez les logs pour `hermes-wiki: standalone mode` ou `extension mode`
- Le répertoire doit être `~/.hermes/plugins/hermes_wiki/` (tiret bas, pas tiret)

**Aucune page wiki générée ?**
- Vérifiez que le LLM est configuré : `model.default` et `model.provider` dans config.yaml
- Vérifiez les logs pour `hermes-wiki: LLM failed` — indique un problème d'authentification ou réseau
- Minimum 2 messages par session requis

**Les sujets ne sont pas agrégés ?**
- Vérifiez les logs pour les messages `hermes-wiki: topic aggregation`
- Vérifiez que les dirty markers existent : `sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- L'agrégation de sujets s'exécute toutes les 2 heures ; les nouveaux sujets peuvent prendre jusqu'à 2 heures

**Outil wiki_search non disponible ?**
- Disponible uniquement en mode standalone (pas de plugin holographic)
- En mode extension, utilisez `fact_store(action='search')` à la place

## Licence

MIT
