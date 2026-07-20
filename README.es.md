# hermes-wiki-plugin

Plugin Karpathy LLM Wiki para [Hermes Agent](https://github.com/NousResearch/hermes-agent) — conversión automática de sesiones a páginas wiki con puntuación de calidad, clasificación de temas, extracción de entidades e i18n en 7 idiomas.

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

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
- **Clasificación de temas**: descubrimiento automático y páginas agregadas
- **Extracción de entidades**: identificación de entidades clave
- **Compatible SQLite 3.31+**: Python 3.9+ (sin RETURNING)

## Solución de problemas

**¿Plugin no se carga?**
- Verifica que `~/.hermes/config.yaml` tenga `hermes-wiki` en `plugins.enabled`
- El directorio debe ser `~/.hermes/plugins/hermes_wiki/` (guion bajo, no guion)

## Licencia

MIT
