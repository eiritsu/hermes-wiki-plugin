# hermes-wiki-plugin

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Karpathy LLM Wiki 模式插件，适用于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) —— 自动将对话 session 转换为结构化 wiki 页面，支持质量评分、主题分类、实体提取、跨会话主题聚合和 7 语言 i18n。

## 为什么需要这个插件

Hermes 每天产生大量有价值的对话——调试过程、决策讨论、问题排查、想法碰撞。但这些知识存在三个问题：

- **会话结束后知识就沉没了**。下次遇到类似问题，只记得"上次好像聊过"，但记不清细节。`session_search` 能搜原始对话，但噪声大、上下文碎片化。
- **没有结构化沉淀**。对话是线性的聊天记录，不是按主题、决策、结论组织的文档。
- **跨会话知识无法关联**。同一个话题在不同会话中的讨论、同一个项目的不同阶段，无法串联起来。

## 它能做什么

插件在会话结束时自动调用 LLM，把对话提炼成结构化 wiki 页面。跨多个会话讨论的主题会自动聚合为主题页面，包含跨会话洞察。

- **质量评分**（1-5）：自动过滤噪声，只保留有价值的会话
- **主题分类 + 实体提取**：自动识别"这个会话讨论了什么"
- **关键决策和问题解决**：抽取"做了什么决定、为什么、怎么解决的"
- **Fact 提取**：可复用知识（工具技巧、踩坑经验、workflow 发现）写入长期记忆，下次搜索直接命中
- **主题聚合**：跨会话主题获得 LLM 整合的概述、时间线、实体和演进路径
- **7 语言支持**：对话用什么语言，wiki 就生成什么语言

## 使用场景

**日常对话积累知识库**
不管是问技术问题、讨论工作方案、还是探索新想法，每次对话结束自动生成结构化摘要。日积月累，wiki 就是你和 Hermes 共同构建的知识库。

**问题排查留痕**
遇到报错、排查原因、找到解决方案——这个过程自动沉淀为 wiki 页面。下次再遇到类似问题，搜 wiki 比翻聊天记录快得多。

**决策过程可追溯**
讨论方案、对比选择、做出决定——对话中的思考过程自动归档。事后回顾时能清楚看到"当时为什么选了这个方案"。

**主题跨会话演进**
当你在多个会话中处理同一主题（例如一个功能实现、一次排查调查），插件会自动创建主题页面，整合所有相关会话的洞察——展示演进时间线、跨会话决策和模式。

## 安装

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

安装脚本会将后端安装到 `~/.hermes/plugins/hermes_wiki/`，将 Desktop GUI 插件安装到 `~/.hermes/desktop-plugins/hermes-wiki/`。

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
    → on_session_end 或 on_session_reset hook 触发
      → 从 state.db 读取 session 消息
        → LLM 分析：质量 / 语言 / 主题 / 实体 / 决策 / facts
          → Wiki 页面写入 hermes_wiki_pages（quality >= 4）
          → Facts 提取到 holographic memory（如已激活）
          → 为受影响的主题写入脏标记
  → 每 1 小时 batch scan 兜底（补捞 hook 漏掉的会话）
  → 每 2 小时主题聚合（通过 LLM 处理脏标记主题）
```

### Session 工作流（Wiki）

1. Session 结束 → hook 触发 → 消息入队到 SQLite
2. 后台线程调用 LLM 处理 session 消息
3. LLM 返回：质量评分、语言、主题、实体、关键决策、完整 wiki 内容
4. Wiki 页面写入 `hermes_wiki_pages`（quality >= 4）
5. 为每个 topic slug 写入脏标记到 `hermes_wiki_topic_dirty`

### 主题工作流（Topic 聚合）

1. 每 2 小时，`aggregate_topics()` 读取脏标记
2. 对每个脏主题，获取关联 wiki 页面的 `full_content`
3. LLM 整合跨会话内容：概述、决策、模式、演进
4. 主题页面写入 `hermes_wiki_topics`
5. LLM 成功后清除脏标记；失败时重新标记（下个周期重试）

### 增量处理

两个工作流都使用增量处理来避免重复的 LLM 调用：

- **Wiki**：`hermes_wiki_session_state` 跟踪已处理的 session；batch scan 只处理新增的
- **Topic**：`hermes_wiki_topic_dirty` 标记需要重新聚合的主题；只处理脏主题

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

### Desktop GUI

插件在 Hermes Desktop 中提供双面板侧栏：

- **左侧面板**：Topics（可折叠分组，含子 session）+ All Pages（扁平列表）
- **右侧面板**：详情视图，含工具栏（返回、导出、编辑、删除）、元数据和内容
- **批量选择**：选择模式下可跨 Topics 和 All Pages 勾选
- **主题详情**：展示 LLM 整合的概述、时间线、实体和 session 链接

### 直接查看 wiki 页面

```bash
# 列出所有 wiki 页面
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# 列出所有主题页面
sqlite3 ~/.hermes/memory_store.db \
  "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# 检查待聚合的脏主题
sqlite3 ~/.hermes/memory_store.db \
  "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## 架构

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — 入口、hooks、1h 扫描定时器、topic 模块注册
│   ├── wiki_store.py        — SQLite：hermes_wiki_pages、session_state、pending_queue
│   ├── wiki_builder.py      — LLM session 分析与 wiki 页面生成
│   ├── wiki_rpc.py          — wiki.* RPC 方法（list、get、create、update、delete、stats）
│   ├── llm_client.py        — 共享 LLM HTTP 客户端（provider 解析、Anthropic/OpenAI 格式）
│   ├── rpc_utils.py         — 共享 JSON-RPC 工具（_err、parse_json_columns）
│   ├── topic/
│   │   ├── __init__.py      — topic 模块注册、2h 聚合定时器
│   │   ├── topic_store.py   — SQLite：hermes_wiki_topics、hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — LLM 主题聚合，基于脏标记的增量处理
│   │   └── topic_rpc.py     — topic.* RPC 方法（list、get）
│   ├── prompts/
│   │   ├── wiki.md          — session → wiki 提示词
│   │   └── topic.md         — 主题聚合提示词
│   └── plugin.yaml          — 插件元数据
├── desktop/
│   └── plugin.js            — Hermes Desktop GUI（双面板侧栏、DetailToolbar、批量选择）
├── docs/                    — 多语言 README（zh/ja/ko/de/fr/es）
├── README.md                — 英文文档
└── install.sh               — 安装后端 + Desktop + gateway RPC 补丁
```

### 数据流

```
Session 消息
  → wiki_builder（LLM）→ hermes_wiki_pages（session 类型）
    → wiki_builder 写入脏标记 → hermes_wiki_topic_dirty
      → topic_builder（LLM）读取 wiki 页面 → hermes_wiki_topics
        → Desktop GUI 通过 topic.list / topic.get RPC 读取
```

### 数据库表

| 表名 | 用途 |
|------|------|
| `hermes_wiki_pages` | Session wiki 页面（page_type='session'） |
| `hermes_wiki_session_state` | 跟踪已处理的 session（增量 wiki） |
| `hermes_wiki_pending_queue` | 等待处理的 session 队列 |
| `hermes_wiki_topics` | 主题聚合页面（LLM 整合） |
| `hermes_wiki_topic_dirty` | 增量主题聚合的脏标记 |

### RPC 方法

| 方法 | 描述 |
|------|------|
| `wiki.list` | 列出 session wiki 页面 |
| `wiki.get` | 获取单个 wiki 页面 |
| `wiki.create` | 创建手动 wiki 页面 |
| `wiki.update` | 更新 wiki 页面 |
| `wiki.delete` | 删除 wiki 页面 |
| `wiki.stats` | Wiki 统计信息 |
| `wiki.batch_process` | 批量处理待处理 session |
| `topic.list` | 列出主题页面 |
| `topic.get` | 获取单个主题页面（含关联 session） |

## 功能特性

- **7 语言 i18n**：en/zh/ja/ko/de/fr/es — LLM 自动检测对话语言，wiki 页面用对应语言生成
- **质量评分**：1-5 分制（5=深入且重要，1=噪音），低质量会话只做最小处理
- **主题聚合**：跨会话主题获得 LLM 整合的概述、决策、模式和演进时间线
- **增量处理**：脏标记确保只有变更的主题被重新聚合；LLM 失败时回退重试
- **实体提取**：从对话中识别关键实体（人物、工具、系统）
- **Fact 提取**：可复用知识写入 holographic memory —— 可通过 `fact_store` 搜索
- **双 Hook 触发**：`on_session_end` + `on_session_reset` —— 近实时 wiki 生成
- **共享 LLM 客户端**：provider 解析、Anthropic/OpenAI 格式检测、.env 加载
- **Desktop GUI**：双面板侧栏，含主题分组、批量选择、DetailToolbar、markdown 渲染
- **优雅降级**：LLM 不可用时回退到模板；通过脏标记重试

## 故障排除

**插件未加载？**
- 检查 `~/.hermes/config.yaml` 中 `plugins.enabled` 包含 `hermes-wiki`
- 查看日志中是否有 `hermes-wiki: standalone mode` 或 `extension mode`
- 确认目录为 `~/.hermes/plugins/hermes_wiki/`（下划线，不是连字符）

**没有生成 wiki 页面？**
- 检查 LLM 配置：config.yaml 中的 `model.default` 和 `model.provider`
- 查看日志中是否有 `hermes-wiki: LLM failed` —— 表示认证或网络问题
- 每个 session 至少需要 2 条消息

**主题没有聚合？**
- 查看日志中是否有 `hermes-wiki: topic aggregation` 消息
- 检查脏标记是否存在：`sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- 主题聚合每 2 小时运行一次；新主题可能需要最多 2 小时才能出现

**wiki_search 工具不可用？**
- 仅在独立模式下可用（无 holographic 插件时）
- 扩展模式下请使用 `fact_store(action='search')`

## 许可证

MIT
