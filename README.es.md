# hermes-wiki-plugin

Plugin Karpathy LLM Wiki para [Hermes Agent](https://github.com/NousResearch/hermes-agent) — conversión automática de sesiones a páginas wiki con puntuación de calidad, clasificación de temas, extracción de entidades e i18n en 7 idiomas.

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## ¿Por qué este plugin?

Hermes genera conversaciones valiosas todos los días — sesiones de depuración, discusiones de decisiones, resolución de problemas, exploración de ideas. Pero este conocimiento tiene tres problemas:

- **El conocimiento se hunde al finalizar la sesión.** La próxima vez que enfrentes un problema similar, recuerdas "ya traté algo así" pero no puedes recordar los detalles. `session_search` puede encontrar conversaciones crudas, pero los resultados son ruidosos y fragmentados.
- **Sin acumulación estructurada.** Las conversaciones son registros de chat lineales, no documentos organizados por tema, decisión y resultado.
- **El conocimiento no se puede conectar entre sesiones.** El mismo tema discutido en diferentes sesiones, o diferentes fases del mismo proyecto, no pueden vincularse.

## Qué hace

El plugin llama automáticamente a tu LLM al final de cada sesión, destilando conversaciones en páginas wiki estructuradas:

- **Puntuación de calidad** (1-5): Filtra automáticamente el ruido, manteniendo solo sesiones valiosas
- **Clasificación de temas + extracción de entidades**: Identifica automáticamente "de qué trataba esta conversación"
- **Decisiones clave y resolución de problemas**: Extrae "qué decisiones se tomaron, por qué y cómo se resolvieron los problemas"
- **Extracción de facts**: Conocimiento reutilizable (peculiaridades de herramientas, trampas, descubrimientos de flujos de trabajo) se escribe en memoria a largo plazo, directamente encontrable en búsquedas futuras
- **Soporte para 7 idiomas**: Las páginas wiki se generan en el mismo idioma que la conversación

## Casos de uso

**Las conversaciones diarias construyen una base de conocimiento**
Ya sean preguntas técnicas, discusiones de planes de trabajo o exploración de nuevas ideas, cada conversación genera automáticamente un resumen estructurado. Con el tiempo, el wiki se convierte en una base de conocimiento co-construida por ti y Hermes.

**La resolución de problemas deja rastros**
Encontrar errores, investigar causas, descubrir soluciones — este proceso se cristaliza automáticamente en páginas wiki. La próxima vez que surja un problema similar, buscar en el wiki es mucho más rápido que desplazarse por el historial de chat.

**El historial de decisiones es rastreable**
Discutir enfoques, comparar opciones, tomar decisiones — el proceso de pensamiento se archiva automáticamente. Al revisar después, se ve claramente "por qué elegimos este enfoque".

**Las preferencias y experiencia personal se acumulan**
A través de la extracción de facts, tus hábitos de trabajo, herramientas frecuentes y trampas pasadas se acumulan automáticamente en la memoria a largo plazo. Cuanto más uses Hermes, mejor te entiende.

## Instalación

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

Añade `hermes-wiki` en `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Reinicia Hermes Agent. El plugin usa automáticamente la configuración LLM existente (`model.default` / `model.provider`).

## Funcionamiento

**Completamente automático — sin intervención manual.**

```
Conversación con Hermes
  → Sesión terminada (cambio de tema / reinicio / cierre)
    → Hook on_session_end activado (milisegundos, no bloqueante)
      → Mensajes encolados en SQLite
        → Hilo daemon en segundo plano inicia
          → Llamada LLM (config.yaml)
            → Análisis: calidad / idioma / temas / entidades / decisiones
            → Página wiki estructurada escrita en SQLite
            → Facts extraídos a fact_store
```

## Características

- **i18n 7 idiomas**: en/zh/ja/ko/de/fr/es — el LLM detecta el idioma y genera páginas wiki en el mismo idioma
- **Puntuación de calidad**: escala 1-5 (5=profundo+importante, 1=ruido)
- **Clasificación de temas + Agregación**：descubrimiento automático, reconstrucción de páginas de temas cada 2 horas
- **Extracción de entidades**: identificación de entidades clave
- **Compatible SQLite 3.31+**: Python 3.9+ (sin RETURNING)

## Solución de problemas

**¿Plugin no se carga?**
- Verifica que `~/.hermes/config.yaml` tenga `hermes-wiki` en `plugins.enabled`
- El directorio debe ser `~/.hermes/plugins/hermes_wiki/` (guion bajo, no guion)

## Uso

### Búsqueda de páginas Wiki

**Modo autónomo**:
```
Tú: Busca discusiones de nginx en el wiki
Hermes: [llama a wiki_search(query='nginx')]
  → Devuelve páginas wiki coincidentes
```

**Consejo**: El LLM no siempre prioriza `wiki_search`. Para asegurar resultados del wiki, menciona explícitamente "wiki" en tu consulta:
```
Tú: Usa wiki_search para buscar nuestras discusiones sobre nginx
Tú: Busca en el wiki las actividades de hoy
Tú: Busca en el wiki el trabajo de endpoints personalizados
```

Se admiten consultas de múltiples palabras — la herramienta divide tu consulta en palabras y coincide con cualquiera:
```
Tú: wiki_search para "wiki plugin desarrollo"
  → Coincide con páginas que contengan "wiki" O "plugin" O "desarrollo"
```

## Licencia

MIT
