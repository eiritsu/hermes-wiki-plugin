# hermes-wiki-plugin

Plugin Karpathy LLM Wiki pour [Hermes Agent](https://github.com/NousResearch/hermes-agent) — conversion automatique des sessions en pages wiki avec notation de qualité, classification des sujets, extraction d'entités et i18n en 7 langues.

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## Pourquoi ce plugin ?

Hermes génère chaque jour des conversations précieuses — sessions de débogage, discussions de décisions, résolution de problèmes, exploration d'idées. Mais ces connaissances ont trois problèmes :

- **Le savoir disparaît à la fin de la session.** La prochaine fois que vous rencontrez un problème similaire, vous vous souvenez « j'ai déjà traité quelque chose comme ça » mais les détails manquent. `session_search` peut trouver les conversations brutes, mais les résultats sont bruités et fragmentés.
- **Pas d'accumulation structurée.** Les conversations sont des journaux de chat linéaires, pas des documents organisés par sujet, décision et résultat.
- **Le savoir ne peut pas être lié entre les sessions.** Un même sujet discuté dans différentes sessions, ou différentes phases d'un même projet, ne peuvent pas être reliés.

## Ce qu'il fait

Le plugin appelle automatiquement votre LLM à la fin de chaque session, distillant les conversations en pages wiki structurées :

- **Notation de qualité** (1-5) : Filtre automatiquement le bruit, ne gardant que les sessions valorables
- **Classification des sujets + extraction d'entités** : Identifie automatiquement « de quoi parlait cette conversation »
- **Décisions clés et résolution de problèmes** : Extrait « quelles décisions ont été prises, pourquoi et comment les problèmes ont été résolus »
- **Extraction de facts** : Les connaissances réutilisables (particularités des outils, pièges, découvertes de workflows) sont écrites en mémoire à long terme, directement trouvables lors des futures recherches
- **Support 7 langues** : Les pages wiki sont générées dans la même langue que la conversation

## Cas d'usage

**Les conversations quotidiennes construissent une base de connaissances**
Que ce soit des questions techniques, des discussions de plans de travail ou l'exploration de nouvelles idées, chaque conversation génère automatiquement un résumé structuré. Au fil du temps, le wiki devient une base de connaissances co-construite par vous et Hermes.

**Le dépannage laisse des traces**
Rencontrer des erreurs, enquêter sur les causes, trouver des solutions — ce processus se cristallise automatiquement en pages wiki. La prochaine fois qu'un problème similaire survient, chercher dans le wiki est bien plus rapide que parcourir l'historique des discussions.

**L'historique des décisions est traçable**
Discuter des approches, comparer les options, prendre des décisions — le processus de réflexion est automatiquement archivé. Lors d'une révision ultérieure, on voit clairement « pourquoi nous avons choisi cette approche ».

**Les préférences et l'expérience personnelle s'accumulent**
Grâce à l'extraction de facts, vos habitudes de travail, outils favoris et pièges passés s'accumulent automatiquement en mémoire à long terme. Plus vous utilisez Hermes, mieux il vous comprend.

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
- **Classification des sujets + Agrégation** : découverte automatique, reconstruction des pages de sujets toutes les 2 heures
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
