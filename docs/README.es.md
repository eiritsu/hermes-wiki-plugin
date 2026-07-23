# hermes-wiki-plugin

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Plugin Karpathy LLM Wiki para [Hermes Agent](https://github.com/NousResearch/hermes-agent) — conversión automática de sesiones a páginas wiki con puntuación de calidad, clasificación de temas, extracción de entidades, agregación entre sesiones e i18n en 7 idiomas.

## ¿Por qué este plugin?

Hermes genera conversaciones valiosas todos los días — sesiones de depuración, discusiones de decisiones, resolución de problemas, exploración de ideas. Pero este conocimiento tiene tres problemas:

- **El conocimiento se hunde al finalizar la sesión.** La próxima vez que enfrentes un problema similar, recuerdas "ya traté algo así" pero no puedes recordar los detalles. `session_search` puede encontrar conversaciones crudas, pero los resultados son ruidosos y fragmentados.
- **Sin acumulación estructurada.** Las conversaciones son registros de chat lineales, no documentos organizados por tema, decisión y resultado.
- **El conocimiento no se puede conectar entre sesiones.** El mismo tema discutido en diferentes sesiones, o diferentes fases del mismo proyecto, no pueden vincularse.

## Qué hace

El plugin llama automáticamente a tu LLM al final de cada sesión, destilando conversaciones en páginas wiki estructuradas. Los temas discutidos en múltiples sesiones se agregan automáticamente en páginas de tema con insights entre sesiones.

- **Puntuación de calidad** (1-5): Filtra automáticamente el ruido, manteniendo solo sesiones valiosas
- **Clasificación de temas + extracción de entidades**: Identifica automáticamente "de qué trataba esta conversación"
- **Decisiones clave y resolución de problemas**: Extrae "qué decisiones se tomaron, por qué y cómo se resolvieron los problemas"
- **Extracción de facts**: Conocimiento reutilizable (peculiaridades de herramientas, trampas, descubrimientos de flujos de trabajo) se escribe en memoria a largo plazo, directamente encontrable en búsquedas futuras
- **Agregación de temas**: Los temas entre sesiones obtienen una vista general integrada por LLM, timeline, entidades y camino de evolución
- **Soporte para 7 idiomas**: Las páginas wiki se generan en el mismo idioma que la conversación

## Casos de uso

**Las conversaciones diarias construyen una base de conocimiento**
Ya sean preguntas técnicas, discusiones de planes de trabajo o exploración de nuevas ideas, cada conversación genera automáticamente un resumen estructurado. Con el tiempo, el wiki se convierte en una base de conocimiento co-construida por ti y Hermes.

**La resolución de problemas deja rastros**
Encontrar errores, investigar causas, descubrir soluciones — este proceso se cristaliza automáticamente en páginas wiki. La próxima vez que surja un problema similar, buscar en el wiki es mucho más rápido que desplazarse por el historial de chat.

**El historial de decisiones es rastreable**
Discutir enfoques, comparar opciones, tomar decisiones — el proceso de pensamiento se archiva automáticamente. Al revisar después, se ve claramente "por qué elegimos este enfoque".

**Los temas evolucionan entre sesiones**
Cuando trabajas en el mismo tema en múltiples sesiones (ej. implementación de una funcionalidad, investigación de depuración), el plugin crea automáticamente una página de tema que integra los insights de todas las sesiones relacionadas — mostrando la timeline de evolución, decisiones entre sesiones y patrones.

## Instalación

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

El instalador coloca el backend en `~/.hermes/plugins/hermes_wiki/` y el plugin de GUI Desktop en `~/.hermes/desktop-plugins/hermes-wiki/`.

Luego edita `~/.hermes/config.yaml` — añade `hermes-wiki` a la lista de plugins:

```yaml
plugins:
  enabled:
    - hermes-wiki
    # ... otros plugins que ya tengas
```

Reinicia Hermes Agent para activar.

El plugin usa automáticamente la configuración LLM existente (`model.default` / `model.provider` en config.yaml). No se necesita configuración LLM adicional.

## Funcionamiento

**Completamente automático — sin intervención manual.**

```
Conversación con Hermes
  → Sesión terminada (cambio de tema / reinicio / cierre)
    → Hook on_session_end o on_session_reset activado
      → Mensajes de sesión leídos desde state.db
        → Análisis LLM: calidad / idioma / temas / entidades / decisiones / facts
          → Página wiki escrita en hermes_wiki_pages (quality >= 4)
          → Facts extraídos a holographic memory (si está activo)
          → Dirty markers escritos para los temas afectados
  → Escaneo por lotes cada hora (captura lo que los hooks perdieron)
  → Agregación de temas cada 2 horas (procesa temas dirty vía LLM)
```

### Workflow de sesión (Wiki)

1. Sesión terminada → hook activado → mensajes encolados en SQLite
2. El thread en segundo plano envía mensajes de sesión al LLM
3. El LLM devuelve: puntuación de calidad, idioma, temas, entidades, decisiones clave, contenido wiki completo
4. Página wiki escrita en `hermes_wiki_pages` (quality >= 4)
5. Dirty markers escritos en `hermes_wiki_topic_dirty` para cada slug de tema

### Workflow de tema (Agregación)

1. Cada 2 horas, `aggregate_topics()` lee los dirty markers
2. Para cada tema dirty, obtiene el `full_content` de las páginas wiki asociadas
3. El LLM integra contenido entre sesiones: vista general, decisiones, patrones, evolución
4. Página de tema escrita en `hermes_wiki_topics`
5. Dirty marker eliminado en éxito del LLM; re-marcado en fallback (reintento en el siguiente ciclo)

### Procesamiento incremental

Ambos workflows usan procesamiento incremental para evitar llamadas LLM redundantes:

- **Wiki**: `hermes_wiki_session_state` rastrea sesiones procesadas; el escaneo por lotes solo procesa las nuevas
- **Tema**: `hermes_wiki_topic_dirty` marca temas que necesitan re-agregación; solo los temas dirty se procesan

## Condiciones de activación

| Escenario | Hook | ¿Activa generación wiki? |
|----------|------|--------------------------|
| Cerrar ventana / desconectar / timeout de inactividad | `on_session_end` | ✅ Inmediato |
| Cambio de tema / `/new` | `on_session_reset` | ✅ Inmediato |
| Sesión existente recibe mensajes | escaneo por lotes | ✅ Dentro de 1 hora |
| Sesión de cron job | — | ❌ Omitido |
| Sesión de subagent | — | ❌ Omitido |
| Menos de 2 mensajes | — | ❌ Omitido |

## Dos modos

El plugin detecta automáticamente qué modo usar al iniciar:

### Modo Extension (plugin holographic memory activo)
- Comparte la conexión SQLite de holographic
- `fact_store(action='search', query="...")` incluye automáticamente resultados wiki junto con facts
- No se necesitan herramientas adicionales — una búsqueda cubre todo

### Modo Standalone (sin holographic)
- Gestiona su propia conexión SQLite
- Añade la herramienta `wiki_search` para consultar páginas wiki
- Funciona independientemente de cualquier otro plugin de memoria
- La herramienta se registra en el toolset `memory`

## Uso

### Búsqueda de páginas Wiki

**Modo Extension** (holographic activo):
```
Tú: ¿Qué discutimos sobre la configuración de nginx?
Hermes: [llama a fact_store(action='search', query='nginx')]
  → Devuelve facts + páginas wiki en una sola búsqueda
```

**Modo Standalone**:
```
Tú: Busca discusiones de nginx en el wiki
Hermes: [llama a wiki_search(query='nginx')]
  → Devuelve páginas wiki coincidentes
```

### GUI Desktop

El plugin proporciona una sidebar de doble panel en Hermes Desktop:

- **Panel izquierdo**: Temas (grupos colapsables con hijos de sesiones) + Todas las páginas (lista plana)
- **Panel derecho**: Vista detallada con barra de herramientas (atrás, exportar, editar, eliminar), metadatos y contenido
- **Selección por lotes**: Modo selección con casillas en Temas y Todas las páginas
- **Detalle de tema**: Vista general integrada por LLM, timeline, entidades y enlaces de sesiones

### Ver páginas Wiki directamente

```bash
# Listar todas las páginas wiki
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# Listar todas las páginas de temas
sqlite3 ~/.hermes/memory_store.db \
  "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# Verificar temas dirty pendientes de agregación
sqlite3 ~/.hermes/memory_store.db \
  "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## Arquitectura

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — punto de entrada, hooks, timer de escaneo 1h, registro de módulo de temas
│   ├── wiki_store.py        — SQLite: hermes_wiki_pages, session_state, pending_queue
│   ├── wiki_builder.py      — Análisis LLM de sesión y generación de páginas wiki
│   ├── wiki_rpc.py          — Métodos RPC wiki.* (list, get, create, update, delete, stats)
│   ├── llm_client.py        — Cliente HTTP LLM compartido (resolución de provider, Anthropic/OpenAI)
│   ├── rpc_utils.py         — Utilidades JSON-RPC compartidas (_err, parse_json_columns)
│   ├── topic/
│   │   ├── __init__.py      — Registro de módulo de temas, timer de agregación 2h
│   │   ├── topic_store.py   — SQLite: hermes_wiki_topics, hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — Agregación LLM de temas con procesamiento incremental dirty-marker
│   │   └── topic_rpc.py     — Métodos RPC topic.* (list, get)
│   ├── prompts/
│   │   ├── default.md       — Prompt de análisis de sesión
│   │   └── topic.md         — Prompt de agregación de temas
│   └── plugin.yaml          — Metadatos del plugin
├── desktop/
│   └── plugin.js            — GUI Hermes Desktop (sidebar doble panel, DetailToolbar, selección por lotes)
├── docs/                    — READMEs multilingües (zh/ja/ko/de/fr/es)
├── README.md                — Documentación en inglés
└── install.sh               — Instala backend + desktop + parche de gateway RPC
```

### Flujo de datos

```
Mensajes de sesión
  → wiki_builder (LLM) → hermes_wiki_pages (tipo sesión)
    → wiki_builder escribe dirty markers → hermes_wiki_topic_dirty
      → topic_builder (LLM) lee páginas wiki → hermes_wiki_topics
        → GUI Desktop lee vía topic.list / topic.get RPC
```

### Tablas de base de datos

| Tabla | Propósito |
|-------|---------|
| `hermes_wiki_pages` | Páginas wiki de sesiones (page_type='session') |
| `hermes_wiki_session_state` | Rastreo de sesiones procesadas (wiki incremental) |
| `hermes_wiki_pending_queue` | Cola de sesiones pendientes de procesamiento |
| `hermes_wiki_topics` | Páginas de agregación de temas (LLM integrado) |
| `hermes_wiki_topic_dirty` | Dirty markers para agregación incremental de temas |

### Métodos RPC

| Método | Descripción |
|--------|-------------|
| `wiki.list` | Listar páginas wiki de sesiones |
| `wiki.get` | Obtener una página wiki individual |
| `wiki.create` | Crear página wiki manual |
| `wiki.update` | Actualizar página wiki |
| `wiki.delete` | Eliminar página wiki |
| `wiki.stats` | Estadísticas del wiki |
| `wiki.batch_process` | Procesar por lotes sesiones pendientes |
| `topic.list` | Listar páginas de temas |
| `topic.get` | Obtener página de tema individual con sesiones |

## Características

- **i18n 7 idiomas**: en/zh/ja/ko/de/fr/es — el LLM detecta el idioma de la conversación y genera páginas wiki en ese idioma
- **Puntuación de calidad**: escala 1-5 (5=profundo+importante, 1=ruido), las sesiones de baja calidad se procesan al mínimo
- **Agregación de temas**: los temas entre sesiones obtienen vista general integrada por LLM, decisiones, patrones y timeline de evolución
- **Procesamiento incremental**: los dirty markers aseguran que solo los temas modificados se re-agregan; fallback en caso de fallo LLM
- **Extracción de entidades**: identifica entidades clave (personas, herramientas, sistemas) de las conversaciones
- **Extracción de facts**: conocimiento reutilizable escrito en holographic memory — buscable vía `fact_store`
- **Doble hook de activación**: `on_session_end` + `on_session_reset` — generación wiki casi instantánea
- **Cliente LLM compartido**: resolución de provider, detección de formato Anthropic/OpenAI, carga de .env
- **GUI Desktop**: sidebar doble panel con grupos de temas, selección por lotes, DetailToolbar, renderizado markdown
- **Degradación elegante**: fallback a template cuando el LLM no está disponible; reintento vía dirty markers

## Solución de problemas

**¿Plugin no se carga?**
- Verifica que `~/.hermes/config.yaml` tenga `hermes-wiki` en `plugins.enabled`
- Verifica los logs para `hermes-wiki: standalone mode` o `extension mode`
- El directorio debe ser `~/.hermes/plugins/hermes_wiki/` (guion bajo, no guion)

**¿No se generan páginas wiki?**
- Verifica que el LLM esté configurado: `model.default` y `model.provider` en config.yaml
- Verifica los logs para `hermes-wiki: LLM failed` — indica problema de autenticación o red
- Mínimo 2 mensajes por sesión requeridos

**¿Los temas no se agregan?**
- Verifica los logs para mensajes de `hermes-wiki: topic aggregation`
- Verifica que existan dirty markers: `sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- La agregación de temas se ejecuta cada 2 horas; los nuevos temas pueden tardar hasta 2 horas en aparecer

**¿Herramienta wiki_search no disponible?**
- Solo disponible en modo standalone (sin plugin holographic)
- En modo extension, usa `fact_store(action='search')` en su lugar

## Licencia

MIT
