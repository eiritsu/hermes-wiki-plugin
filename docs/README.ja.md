# hermes-wiki-plugin

> 🌐 [English](../README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

[Hermes Agent](https://github.com/NousResearch/hermes-agent) の Karpathy LLM Wiki パターンプラグイン — セッションから wiki ページへの自動変換、品質スコアリング、トピック分類、エンティティ抽出、セッション横断トピック集約、7言語 i18n 対応。

## なぜこのプラグインが必要か

Hermesは毎日大量の価値ある会話を生み出します——デバッグ、意思決定の議論、問題解決、アイデアの探求。しかし、この知識には3つの問題があります：

- **セッション終了とともに知識が沈む**。次に類似の問題に直面したとき、「前にこんなことをやった気がする」と思うだけで、詳細を思い出せない。`session_search`で生の会話を検索できるが、ノイズが多く文脈が断片化している。
- **構造化された蓄積がない**。会話はリニアなチャットログであり、トピック・決定・結論別に整理されたドキュメントではない。
- **セッション横断の知識を関連づけられない**。同じトピックが異なるセッションで議論されたり、同じプロジェクトの異なるフェーズがつなげられない。

## このプラグインの機能

セッション終了時に自動的にLLMを呼び、会話を構造化されたwikiページに蒸留します。複数セッションにわたって議論されたトピックは、自動的にトピックページに集約され、セッション横断の洞察が得られます：

- **品質スコアリング**（1-5）：ノイズを自動フィルタリングし、価値あるセッションのみ保持
- **トピック分類 + エンティティ抽出**：「この会話が何についてだったか」を自動識別
- **重要な決定と問題解決**：「何を決定し、なぜ、どのように問題を解決したか」を抽出
- **Fact抽出**：再利用可能な知識（ツールの癖、ハマりポイント、ワークフローの発見）を長期メモリに書き込み、将来の検索で直接ヒット
- **トピック集約**：セッション横断のトピックにLLM統合の概要、タイムライン、エンティティ、進化パスを生成
- **7言語対応**：会話と同じ言語でwikiページを生成

## ユースケース

**日常会話が知識ベースに**
技術的な質問でも、仕事の計画の議論でも、新しいアイデアの探索でも、各会話の終了時に自動的に構造化された要約が生成されます。日を重ねるごとに、wikiはあなたとHermesが共に構築する知識ベースになります。

**トラブルシューティングが痕跡を残す**
エラーの発生、原因の調査、解決策の発見——このプロセスが自動的にwikiページとして結晶化します。次に類似の問題が起きたとき、wikiを検索する方がチャット履歴をスクロールするよりはるかに高速です。

**意思決定の履歴が追跡可能に**
アプローチの議論、選択肢の比較、決定の実行——思考プロセスが自動的にアーカイブされます。後で見直したとき、「なぜこのアプローチを選んだのか」が明確にわかります。

**トピックがセッション横断で進化する**
複数セッションにわたって同じトピックに取り組む場合（例：機能実装、デバッグ調査）、プラグインは関連するすべてのセッションから洞察を統合したトピックページを自動作成します——進化のタイムライン、セッション横断の決定、パターンを表示します。

## インストール

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

インストーラは backend を `~/.hermes/plugins/hermes_wiki/` に、Desktop GUI プラグインを `~/.hermes/desktop-plugins/hermes-wiki/` に配置します。

`~/.hermes/config.yaml` に `hermes-wiki` を追加：

```yaml
plugins:
  enabled:
    - hermes-wiki
    # ... 他のプラグイン
```

Hermes Agent を再起動で有効化。プラグインは config.yaml の既存 LLM 設定（`model.default` / `model.provider`）を自動使用します。追加の LLM 設定は不要です。

## 仕組み

**完全自動 — 手動操作不要。**

```
Hermesと会話する
  → セッション終了（クローズ / トピック切替 / リセット）
    → on_session_end または on_session_reset フック発火
      → state.dbからセッションメッセージを読み取り
        → LLMが分析：品質 / 言語 / トピック / エンティティ / 決定 / facts
          → wikiページをhermes_wiki_pagesに書き込み（quality >= 4）
          → factsをholographic memoryに抽出（有効時）
          → 対象トピックにダーティマーカーを書き込み
  → 1時間ごとのバッチスキャン（フックが見逃したものを補足）
  → 2時間ごとのトピック集約（ダーティトピックをLLMで処理）
```

### セッションワークフロー（Wiki）

1. セッション終了 → フック発火 → メッセージをSQLiteにキューイング
2. バックグラウンドスレッドがセッションメッセージでLLMを呼び出し
3. LLMが返す：品質スコア、言語、トピック、エンティティ、重要な決定、wiki本文
4. wikiページを `hermes_wiki_pages` に書き込み（quality >= 4）
5. 各トピックslugに対して `hermes_wiki_topic_dirty` にダーティマーカーを書き込み

### トピックワークフロー（トピック集約）

1. 2時間ごとに `aggregate_topics()` がダーティマーカーを読み取り
2. ダーティなトピックごとに、関連wikiページの `full_content` を取得
3. LLMがセッション横断の内容を統合：概要、決定、パターン、進化
4. トピックページを `hermes_wiki_topics` に書き込み
5. LLM成功時にダーティマーカーをクリア；フォールバック時は再マーカー（次サイクルでリトライ）

### インクリメンタル処理

両ワークフローはインクリメンタル処理を使用し、冗長なLLM呼び出しを回避：

- **Wiki**: `hermes_wiki_session_state` が処理済みセッションを追跡；バッチスキャンは新しいセッションのみ処理
- **Topic**: `hermes_wiki_topic_dirty` が再集約が必要なトピックをマーク；ダーティなトピックのみ処理

## トリガー条件

| シナリオ | Hook | wiki生成 |
|----------|------|----------|
| ウィンドウ閉じ / 切断 / アイドルタイムアウト | `on_session_end` | ✅ 即座 |
| トピック切替 / `/new` | `on_session_reset` | ✅ 即座 |
| 既存セッションにメッセージ追加 | batch scan | ✅ 1時間以内 |
| Cron job セッション | — | ❌ スキップ |
| Subagent セッション | — | ❌ スキップ |
| メッセージ2件未満 | — | ❌ スキップ |

## 2つのモード

起動時に自動検出：

### 拡張モード（holographic メモリプラグイン有効時）
- holographic の SQLite 接続を共有
- `fact_store(action='search', query="...")` が wiki 結果を自動含む
- 追加ツール不要 — 1回の検索で全てをカバー

### スタンドアロンモード（holographic なし）
- 独自の SQLite 接続を管理
- `wiki_search` ツールを追加してwikiページをクエリ
- 他のメモリプラグインから独立して動作
- ツールは `memory` toolset に登録

## 使用方法

### wiki ページの検索

**拡張モード**（holographic 有効時）：
```
あなた：nginx に関する議論は？
Hermes：[fact_store(action='search', query='nginx') を呼び出し]
  → facts + wiki ページを一括返却
```

**スタンドアロンモード**：
```
あなた：nginx に関する議論を wiki で検索
Hermes：[wiki_search(query='nginx') を呼び出し]
  → 一致する wiki ページを返す
```

### Desktop GUI

プラグインは Hermes Desktop にデュアルパネルサイドバーを提供：

- **左パネル**：Topics（セッション子要素付き折りたたみグループ）+ All Pages（フラットリスト）
- **右パネル**：ツールバー（戻る、エクスポート、編集、削除）、メタデータ、コンテンツを表示する詳細ビュー
- **バッチ選択**：Topics と All Pages の両方でチェックボックス付きセレクトモード
- **トピック詳細**：LLM統合の概要、タイムライン、エンティティ、セッションリンクを表示

### 直接的な確認

```bash
# 全 wiki ページを表示
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM hermes_wiki_pages WHERE page_type='session' ORDER BY date DESC"

# 全トピックページを表示
sqlite3 ~/.hermes/memory_store.db \
  "SELECT slug, title, session_count FROM hermes_wiki_topics ORDER BY updated_at DESC"

# 集約待ちのダーティトピックを確認
sqlite3 ~/.hermes/memory_store.db \
  "SELECT topic_slug, dirty_at FROM hermes_wiki_topic_dirty"
```

## アーキテクチャ

```text
hermes-wiki-plugin/
├── backend/
│   ├── __init__.py          — エントリポイント、フック、1hスキャンタイマー、トピックモジュール登録
│   ├── wiki_store.py        — SQLite: hermes_wiki_pages, session_state, pending_queue
│   ├── wiki_builder.py      — LLMセッション分析とwikiページ生成
│   ├── wiki_rpc.py          — wiki.* RPCメソッド（list, get, create, update, delete, stats）
│   ├── llm_client.py        — 共有LLM HTTPクライアント（プロバイダー解決、Anthropic/OpenAI）
│   ├── rpc_utils.py         — 共有JSON-RPCユーティリティ（_err, parse_json_columns）
│   ├── topic/
│   │   ├── __init__.py      — トピックモジュール登録、2h集約タイマー
│   │   ├── topic_store.py   — SQLite: hermes_wiki_topics, hermes_wiki_topic_dirty
│   │   ├── topic_builder.py — LLMトピック集約（ダーティマーカーインクリメンタル処理）
│   │   └── topic_rpc.py     — topic.* RPCメソッド（list, get）
│   ├── prompts/
│   │   ├── wiki.md          — session → wiki プロンプト
│   │   └── topic.md         — トピック集約プロンプト
│   └── plugin.yaml          — プラグインメタデータ
├── desktop/
│   └── plugin.js            — Hermes Desktop GUI（デュアルパネルサイドバー、DetailToolbar、バッチ選択）
├── docs/                    — 多言語README（zh/ja/ko/de/fr/es）
├── README.md                — 英語ドキュメント
└── install.sh               — backend + desktop + gateway RPC パッチをインストール
```

### データフロー

```
セッションメッセージ
  → wiki_builder (LLM) → hermes_wiki_pages (session type)
    → wiki_builderがダーティマーカーを書き込み → hermes_wiki_topic_dirty
      → topic_builder (LLM) がwikiページを読み取り → hermes_wiki_topics
        → Desktop GUIがtopic.list / topic.get RPCで読み取り
```

### データベーステーブル

| テーブル | 用途 |
|----------|------|
| `hermes_wiki_pages` | セッションwikiページ（page_type='session'） |
| `hermes_wiki_session_state` | 処理済みセッションの追跡（インクリメンタルwiki） |
| `hermes_wiki_pending_queue` | 処理待ちセッションのキュー |
| `hermes_wiki_topics` | トピック集約ページ（LLM統合） |
| `hermes_wiki_topic_dirty` | インクリメンタルトピック集約用ダーティマーカー |

### RPCメソッド

| メソッド | 説明 |
|----------|------|
| `wiki.list` | セッションwikiページの一覧 |
| `wiki.get` | 単一wikiページの取得 |
| `wiki.create` | 手動wikiページの作成 |
| `wiki.update` | wikiページの更新 |
| `wiki.delete` | wikiページの削除 |
| `wiki.stats` | wiki統計 |
| `wiki.batch_process` | 保留セッションのバッチ処理 |
| `topic.list` | トピックページの一覧 |
| `topic.get` | セッション付き単一トピックページの取得 |

## 機能

- **7言語i18n**: en/zh/ja/ko/de/fr/es — LLMがセッション言語を検出し、その言語でwikiページを生成
- **品質スコアリング**: 1-5スケール（5=深く重要、1=ノイズ）、低品質セッションは最小限の処理
- **トピック集約**: セッション横断のトピックにLLM統合の概要、決定、パターン、進化タイムライン
- **インクリメンタル処理**: ダーティマーカーで変更されたトピックのみ再集約；LLM失敗時はフォールバックリトライ
- **エンティティ抽出**: 会話から重要なエンティティ（人物、ツール、システム）を識別
- **Fact抽出**: 再利用可能な知識をholographic memoryに書き込み — `fact_store`で検索可能
- **デュアルフックトリガー**: `on_session_end` + `on_session_reset` — ほぼリアルタイムにwiki生成
- **共有LLMクライアント**: プロバイダー解決、Anthropic/OpenAIフォーマット検出、.env読み込み
- **Desktop GUI**: トピックグループ、バッチ選択、DetailToolbar、markdownレンダリング付きデュアルパネルサイドバー
- **グレースフルデグレード**: LLM利用不可時にテンプレートにフォールバック；ダーティマーカー経由でリトライ

## トラブルシューティング

**プラグインが読み込まれない？**
- `~/.hermes/config.yaml` の `plugins.enabled` に `hermes-wiki` があるか確認
- ログに `hermes-wiki: standalone mode` または `extension mode` がないか確認
- ディレクトリが `~/.hermes/plugins/hermes_wiki/`（アンダースコア、ハイフンではない）か確認

**wiki ページが生成されない？**
- LLM 設定を確認：`model.default` と `model.provider`
- ログに `hermes-wiki: LLM failed` がないか確認 — 認証またはネットワークの問題
- セッションあたり最低2メッセージ必要

**トピックが集約されない？**
- ログに `hermes-wiki: topic aggregation` メッセージがないか確認
- ダーティマーカーの存在を確認：`sqlite3 ~/.hermes/memory_store.db "SELECT * FROM hermes_wiki_topic_dirty"`
- トピック集約は2時間ごとに実行；新しいトピックは最大2時間かかる場合あり

**wiki_search ツールが利用できない？**
- スタンドアロンモード（holographic プラグインなし）でのみ利用可能
- 拡張モードでは `fact_store(action='search')` を使用

## ライセンス

MIT
