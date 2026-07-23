# hermes-wiki-plugin

[Hermes Agent](https://github.com/NousResearch/hermes-agent) 的 Karpathy LLM Wiki 模式插件 — 自动将对话 session 转换为结构化 wiki 页面，支持质量评分、主题分类、实体提取和 7 语言 i18n。

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## 为什么需要这个插件

Hermes 每天产生大量有价值的对话——调试过程、决策讨论、问题排查、想法碰撞。但这些知识存在三个问题：

- **会话结束后知识就沉没了**。下次遇到类似问题，只记得"上次好像聊过"，但记不清细节。`session_search` 能搜原始对话，但噪声大、上下文碎片化。
- **没有结构化沉淀**。对话是线性的聊天记录，不是按主题、决策、结论组织的文档。
- **跨会话知识无法关联**。同一个话题在不同会话中的讨论、同一个项目的不同阶段，无法串联起来。

## 它能做什么

插件在会话结束时自动调用 LLM，把对话提炼成结构化 wiki 页面：

- **质量评分**（1-5）：自动过滤噪声，只保留有价值的会话
- **主题分类 + 实体提取**：自动识别"这个会话讨论了什么"
- **关键决策和问题解决**：抽取"做了什么决定、为什么、怎么解决的"
- **Fact 提取**：把可复用的知识（工具技巧、踩坑经验、个人偏好）写入长期记忆，下次搜索直接命中
- **7 语言支持**：对话用什么语言，wiki 就生成什么语言

## 使用场景

**日常对话积累知识库**
不管是问技术问题、讨论工作方案、还是探索新想法，每次对话结束自动生成结构化摘要。日积月累，wiki 就是你和 Hermes 共同构建的知识库。

**问题排查留痕**
遇到报错、排查原因、找到解决方案——这个过程自动沉淀为 wiki 页面。下次再遇到类似问题，搜 wiki 比翻聊天记录快得多。

**决策过程可追溯**
讨论方案、对比选择、做出决定——对话中的思考过程自动归档。事后回顾时能清楚看到"当时为什么选了这个方案"。

**个人偏好和经验积累**
通过 fact 提取，你的工作习惯、常用工具、踩过的坑会自动积累到长期记忆。Hermes 越用越懂你。

## 安装

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

安装脚本会将后端安装到 `~/.hermes/plugins/hermes_wiki/`，将 Desktop Wiki GUI 安装到 `~/.hermes/desktop-plugins/hermes-wiki/`。

编辑 `~/.hermes/config.yaml`，将 `hermes-wiki` 添加到插件列表：

```yaml
plugins:
  enabled:
    - hermes-wiki
    # ... 其他已启用的插件
```

重启 Hermes Agent 即可生效。插件会自动使用你在 config.yaml 中已配置的 LLM（`model.default` / `model.provider`），无需额外配置。

## 工作原理

**完全自动化，无需手动操作。**

```
你和 Hermes 对话
  → Session 结束（关闭 / 切换话题 / 重置）
    → on_session_end 或 on_session_reset hook 触发（毫秒级，不阻塞）
      → 若 hook 未传消息，从 state.db 读取
        → 消息入队到 SQLite（按日期分段）
          → 后台 daemon 线程启动
            → 调用你已配置的 LLM（来自 config.yaml）
              → 分析：质量评分 / 语言检测 / 主题 / 实体 / 关键决策 / facts
              → 写入结构化 wiki 页面到 SQLite（quality >= 4）
              → 提取可复用 facts 到 holographic memory（扩展模式下）
  → 每 1 小时 batch scan 兜底（补捞 hook 漏掉的会话）
  → 每 2 小时 topic 聚合（从 session 页面重建主题页面）
```

插件会在首次运行时自动在 `~/.hermes/memory_store.db` 中创建所需的 SQLite 表（`hermes_wiki_pages`、`hermes_wiki_pending_queue` 和 `hermes_wiki_session_state`）。无需手动建表。

## 触发条件

| 场景 | Hook | 是否触发 wiki 生成？ |
|------|------|---------------------|
| 关闭窗口 / 断连 / 超时 | `on_session_end` | ✅ 立即 |
| 切换话题 / `/new` | `on_session_reset` | ✅ 立即 |
| 已有会话新增消息 | batch scan | ✅ 1 小时内 |
| Cron job 会话 | — | ❌ 跳过 |
| 子代理会话 | — | ❌ 跳过 |
| 消息少于 2 条 | — | ❌ 跳过 |

## 两种模式

插件启动时自动检测使用哪种模式：

### 扩展模式（holographic 记忆插件已激活）
- 共享 holographic 的 SQLite 连接
- `fact_store(action='search', query="...")` 自动包含 wiki 结果
- 无需额外工具，一次搜索覆盖全部

### 独立模式（无 holographic）
- 自己管理 SQLite 连接
- 添加 `wiki_search` 工具用于查询 wiki 页面
- 独立于其他记忆插件工作
- 工具注册在 `memory` toolset

## 使用方式

### 搜索 wiki 页面

**扩展模式**（holographic 已激活）：
```
你：之前聊过的 nginx 配置是什么？
Hermes：[调用 fact_store(action='search', query='nginx')]
  → 返回 facts + wiki 页面，一步搜索
```

**独立模式**：
```
你：搜索 wiki 中关于 nginx 的讨论
Hermes：[调用 wiki_search(query='nginx')]
  → 返回匹配的 wiki 页面
```

**提示**：LLM 不一定会优先使用 `wiki_search`。为确保获得 wiki 结果，请在查询中明确提及"wiki"：
```
你：用 wiki_search 搜索我们关于 nginx 的讨论
你：Wiki 搜索今天的活动
你：搜索 wiki 中关于自定义端点的工作
```

支持多词查询——工具会将查询拆分为单词并匹配任意一个：
```
你：wiki_search 搜索 "wiki 插件开发"
  → 匹配包含 "wiki" 或 "插件" 或 "开发" 的页面
```

### 直接查看 wiki 页面

```bash
# 列出所有 wiki 页面
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# 按关键词搜索
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, summary FROM hermes_wiki_pages WHERE title LIKE '%关键词%' OR summary LIKE '%关键词%'"

# 检查待处理队列
sqlite3 ~/.hermes/memory_store.db \
  "SELECT COUNT(*) FROM hermes_wiki_pending_queue WHERE status='pending'"
```

### 验证插件是否生效

1. 查看 Hermes 日志中是否有：`hermes-wiki: standalone mode` 或 `hermes-wiki: extension mode`
2. 几次对话后查询：`sqlite3 ~/.hermes/memory_store.db "SELECT COUNT(*) FROM hermes_wiki_pages"`
3. 使用 Desktop Wiki 侧栏、`wiki_search` 工具（独立模式）或 `fact_store(action='search')`（扩展模式）搜索 wiki 内容

## 功能特性

- **7 语言 i18n**：en/zh/ja/ko/de/fr/es — LLM 自动检测对话语言，wiki 页面用对应语言生成
- **质量评分**：1-5 分制（5=深入且重要，1=噪音），低质量会话只做最小处理
- **主题分类 + 聚合**：自动发现主题，每 2 小时从 session 页面重建主题聚合页面
- **实体提取**：从对话中识别关键实体（人物、工具、系统）
- **Fact 提取**：可复用知识（工具行为、配置坑、用户偏好）写入 holographic memory，可通过 `fact_store` 搜索
- **双 Hook 触发**：`on_session_end` 处理会话关闭 + `on_session_reset` 处理话题切换，近实时生成 wiki
- **Provider 解析**：使用 Hermes 的 `PROVIDER_REGISTRY` — 无硬编码 URL
- **优雅降级**：LLM 不可用时回退到默认分析
- **SQLite 3.31+ 兼容**：支持 Python 3.9+（不使用 RETURNING 子句）

## Wiki 页面结构

每个 wiki 页面包含：

```yaml
---
session_id: "20260718_143022_abc"
date: 2026-07-18
language: en
quality: 4
content_type: troubleshooting
topics: ["docker", "networking"]
entities: ["Docker Compose", "Nginx"]
keywords: ["container", "reverse proxy"]
result: "Resolved container networking issue and configured reverse proxy"
---

# Docker Networking Debug (2026-07-18)

## Background
Container couldn't reach external APIs due to DNS misconfiguration

## Key Decisions
- Used custom bridge network instead of default
- Added explicit DNS resolver in docker-compose.yml

## Problems & Solutions
- DNS timeout → switched to 8.8.8.8 as fallback resolver

## Result
Container networking resolved, reverse proxy configured
```

## 架构

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — 双模式入口、hooks、5 分钟增量扫描 + 2 小时 topic 聚合定时器
│   ├── wiki_store.py        — SQLite 队列、重试、session state、页面存储
│   ├── wiki_builder.py      — LLM 分析与 wiki 页面生成
│   ├── wiki_rpc.py          — Desktop GUI 的 Gateway RPC 方法
│   ├── plugin.yaml          — 插件元数据
│   └── prompts/default.md   — 分析提示词
├── desktop/plugin.js         — Hermes Desktop Wiki 侧栏 GUI（双面板布局，运行时 CSS 注入兼容 Tailwind）
└── install.sh                — 同时安装后端和 Desktop 组件
```

## 故障排除

**插件未加载？**
- 检查 `~/.hermes/config.yaml` 中 `plugins.enabled` 包含 `hermes-wiki`
- 查看日志中是否有 `hermes-wiki: standalone mode` 或 `extension mode`
- 确认目录为 `~/.hermes/plugins/hermes_wiki/`（下划线，不是连字符）

**没有生成 wiki 页面？**
- 检查 LLM 配置：config.yaml 中的 `model.default` 和 `model.provider`
- 查看日志中是否有 `hermes-wiki: LLM failed` — 表示认证或网络问题
- 每个 session 至少需要 2 条消息

**wiki_search 工具不可用？**
- 仅在独立模式下可用（无 holographic 插件时）
- 扩展模式下请使用 `fact_store(action='search')`

## 许可证

MIT
