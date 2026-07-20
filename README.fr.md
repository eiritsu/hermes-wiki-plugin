# hermes-wiki-plugin

Plugin Karpathy LLM Wiki pour [Hermes Agent](https://github.com/NousResearch/hermes-agent) — conversion automatique des sessions en pages wiki avec notation de qualité, classification des sujets, extraction d'entités et i18n en 7 langues.

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## Installation

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

Ajoutez `hermes-wiki` dans `~/.hermes/config.yaml` :

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Redémarrez Hermes Agent. Le plugin utilise automatiquement la configuration LLM existante (`model.default` / `model.provider`).

## Fonctionnement

**Entièrement automatique — aucune intervention manuelle requise.**

```
Conversation avec Hermes
  → Session terminée (changement de sujet / réinitialisation / fermeture)
    → Hook on_session_end déclenché (millisecondes, non bloquant)
      → Messages mis en file d'attente dans SQLite
        → Thread daemon en arrière-plan démarre
          → Appel LLM (config.yaml)
            → Analyse : qualité / langue / sujets / entités / décisions
            → Page wiki structurée écrite dans SQLite
            → Facts extraits dans fact_store
```

## Fonctionnalités

- **i18n 7 langues** : en/zh/ja/ko/de/fr/es — le LLM détecte la langue et génère les pages wiki dans la même langue
- **Notation de qualité** : échelle 1-5 (5=profond+important, 1=bruit)
- **Classification des sujets** : découverte automatique et pages agrégées
- **Extraction d'entités** : identification des entités clés
- **Compatible SQLite 3.31+** : Python 3.9+ (sans RETURNING)

## Dépannage

**Plugin non chargé ?**
- Vérifiez que `~/.hermes/config.yaml` contient `hermes-wiki` dans `plugins.enabled`
- Le répertoire doit être `~/.hermes/plugins/hermes_wiki/` (tiret bas, pas tiret)

## Utilisation

### Recherche de pages Wiki

**Mode autonome** :
```
Toi : Recherche les discussions nginx dans le wiki
Hermes : [appelle wiki_search(query='nginx')]
  → Retourne les pages wiki correspondantes
```

**Astuce** : Le LLM ne privilégie pas toujours `wiki_search`. Pour garantir des résultats wiki, mentionne explicitement "wiki" dans ta requête :
```
Toi : Utilise wiki_search pour trouver nos discussions sur nginx
Toi : Recherche wiki des activités d'aujourd'hui
Toi : Recherche dans le wiki le travail sur les endpoints personnalisés
```

Les requêtes multi-mots sont supportées — l'outil découpe votre requête en mots et correspond à n'importe lequel :
```
Toi : wiki_search pour "wiki plugin développement"
  → Correspond aux pages contenant "wiki" OU "plugin" OU "développement"
```

## Licence

MIT
