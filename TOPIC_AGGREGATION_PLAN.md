# Wiki Topic Aggregation — 完整改动规划

## 目标

在保留单 session wiki 页面的基础上，新增 Obsidian 风格的 Topic 聚合页面。
侧边栏从扁平列表改为树形结构：Topics 区 + All Pages 区。

## 回滚方案

当前 GitHub `main` 分支 commit: `fa9d55b`
所有改动在独立分支 `feat/topic-aggregation` 上开发，合并前可随时回滚：
```
git checkout main && git pull origin main
bash install.sh  # 恢复到 fa9d55b
```

---

## 一、后端改动

### 1.1 Topic 页面自动生成（wiki_builder.py）

**位置**：`_process_session()` 末尾，fact 提取之后

**逻辑**：
```
for topic in analysis.get("topics", []):
    existing = store.get_topic_page(topic)
    if existing:
        # 追加 timeline 条目
        append_session_to_topic(existing, session_meta)
    else:
        # 创建新 topic 页面
        create_topic_page(topic, [session_meta])
```

**Topic 页面结构**：
```markdown
---
page_type: topic
topic: wiki-plugin-development
updated: 2026-07-22
session_count: 4
---

# Wiki Plugin Development

## Overview
{LLM 生成的一句话概述，每次有新 session 时重新生成}

## Timeline
- [[2026-07-22_wiki插件开发fact提取与hook修复]] — fact提取 + hook修复
- [[2026-07-20_hermes-wiki-插件开发与pr提交]] — 初始插件开发

## Key Decisions
- 从 session wiki 的 decisions 字段聚合，去重

## Entities
- 从 session wiki 的 entities 字段聚合，去重
```

**Topic 概述更新策略**：
- 新 session 加入时，用轻量 LLM 调用重新生成 Overview（只传 topic 下的 title + summary 列表，不传全文）
- Timeline / Decisions / Entities 是增量追加，不需要 LLM

### 1.2 Topic 页面存储（wiki_store.py）

**新增方法**：
- `get_topic_page(topic_slug)` → 返回 topic wiki page 或 None
- `update_topic_page(topic_slug, content, session_count, ...)` → 更新或创建
- `list_topics()` → 返回所有 topic 及其关联的 session pages（GROUP BY topics）

**注意**：现有 `_cleanup()` 会删除 `page_type='topic'` 的页面，需要移除这行。

### 1.3 新增 RPC 方法（wiki_rpc.py）

- `wiki.list_topics` → 返回 topics 列表，每个 topic 包含：slug, title, session_count, latest_date, avg_quality
- `wiki.get_topic` → 返回 topic 页面的 full_content + 关联的 session pages 列表
- `wiki.list` 修改 → 增加 `page_type` 过滤参数（session / topic / all）

### 1.4 LLM 调用优化

Topic Overview 更新时，不需要完整的 LLM 分析，只需：
- System prompt: "Write a 2-3 sentence overview for this topic based on the session summaries below."
- Input: topic name + list of (date, title, summary)
- Output: 一句话概述

这比完整 session 分析便宜 10x。

---

## 二、前端改动（desktop/plugin.js）

### 2.1 侧边栏结构

```
Header: 📖 Wiki  |  12 pages  |  [Select] [+] [🔄]
Search: [🔍 Search wiki...]
─────────────────────────────
▼ Topics (3)
  📂 wiki-plugin-development (3)
    ├ 07-22 fact提取与hook修复
    ├ 07-20 插件开发与PR
    └ 07-17 自定义端点
  📂 docker-networking (2)
    ├ 07-15 DNS配置
    └ 07-10 容器网络
  📂 resume-editing (4)
    └ ...
─────────────────────────────
▼ All Pages
  07-22 wiki插件开发fact提取...
  07-21 确认规则与PR修复...
  07-20 自定义端点功能...
─────────────────────────────
[📊 Stats: 12 pages, avg q4.2]
```

### 2.2 新增组件

- `TopicGroup` — 可折叠的 topic 分组，显示 topic 名 + session 数量 + 子页面列表
- `TopicDetail` — topic 聚合页面详情（点击 topic 名进入）
- 修改 `WikiPage` — 主容器，增加 Topics 区和 All Pages 区的切换

### 2.3 交互逻辑

- 点击 topic 名称 → 显示 TopicDetail（聚合页面）
- 点击 topic 下的 session → 显示 WikiDetail（现有详情页）
- Topics 区默认展开，可折叠
- All Pages 区默认折叠，可展开
- 搜索同时搜索 topics 和 session pages

### 2.4 数据流

```
WikiPage 初始化:
  → wiki.list_topics()  // 获取 topics 列表
  → wikiList({ page_type: 'session' })  // 获取 session pages
  → wikiStats()  // 统计信息

点击 Topic:
  → wiki.get_topic(slug)  // 获取 topic 聚合页面 + 关联 sessions

点击 Session:
  → wikiGet(slug)  // 现有逻辑不变
```

---

## 三、实施顺序

| 步骤 | 改动 | 文件 | 风险 |
|------|------|------|------|
| 1 | 移除 _cleanup 中删除 topic 页面的逻辑 | wiki_builder.py | 低 |
| 2 | 新增 topic 页面存储方法 | wiki_store.py | 低 |
| 3 | _process_session 末尾自动更新 topic | wiki_builder.py | 中（LLM 调用） |
| 4 | 新增 wiki.list_topics / wiki.get_topic RPC | wiki_rpc.py | 低 |
| 5 | 本地测试后端 | — | — |
| 6 | 前端侧边栏树形结构 | plugin.js | 中 |
| 7 | 前端 TopicDetail 组件 | plugin.js | 低 |
| 8 | 端到端测试 | — | — |
| 9 | install.sh + 提交 + 推送 | — | — |

---

## 四、回滚检查点

每个步骤完成后打 git tag，失败时可回滚到任意检查点：
- `v0.1-pre-topic` — 当前状态（fa9d55b）
- `v0.2-backend-topic-store` — 步骤 1-2 完成
- `v0.3-backend-topic-builder` — 步骤 3 完成
- `v0.4-backend-rpc` — 步骤 4-5 完成
- `v0.5-frontend` — 步骤 6-7 完成
- `v1.0-topic-aggregation` — 全部完成

---

## 五、已知风险

1. **Topic Overview LLM 调用延迟** — 每次新 session 生成后要额外调一次 LLM。缓解：用轻量 prompt，只传 summary 不传全文
2. **Topic 页面碎片化** — LLM 给出的 topics 可能不一致（如 `docker-networking` vs `docker-config`）。缓解：topic slug 标准化（lowercase, kebab-case），prompt 中约束
3. **_cleanup 删除 topic 页面** — 现有代码会删 page_type='topic' 的页面。必须先移除这行再上线
4. **前端树形结构性能** — topics 多时折叠/展开可能卡。缓解：虚拟列表或懒加载
