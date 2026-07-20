# hermes-wiki-plugin

[Hermes Agent](https://github.com/NousResearch/hermes-agent) の Karpathy LLM Wiki パターンプラグイン — セッションから wiki ページへの自動変換、品質スコアリング、トピック分類、エンティティ抽出、7言語 i18n 対応。

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## インストール

```bash
git clone https://github.com/eiritsu/hermes-wiki-plugin.git /tmp/hermes-wiki-plugin
cd /tmp/hermes-wiki-plugin
bash install.sh
```

`~/.hermes/config.yaml` に `hermes-wiki` を追加：

```yaml
plugins:
  enabled:
    - hermes-wiki
```

Hermes Agent を再起動で有効化。プラグインは config.yaml の既存 LLM 設定（`model.default` / `model.provider`）を自動使用します。追加の LLM 設定は不要です。

## 仕組み

**完全自動 — 手動操作不要。**

```
Hermes と会話
  → セッション終了（トピック切替 / リセット / 閉じる）
    → on_session_end hook 発火（ミリ秒、非ブロック）
      → メッセージを SQLite にキューイング
        → バックグラウンドデーモンスレッド起動
          → LLM 呼び出し（config.yaml の設定を使用）
            → 分析：品質スコア / 言語 / トピック / エンティティ / 決定事項
            → 構造化 wiki ページを SQLite に書き込み
            → facts を fact_store に抽出
```

初回実行時に `~/.hermes/memory_store.db` に SQLite テーブル（`wiki_pages`、`wiki_pending_queue`）を自動作成します。

## トリガー条件

| シナリオ | wiki 生成 |
|----------|----------|
| 通常の会話終了 | ✅ |
| セッション切替 | ✅ |
| セッションリセット | ✅ |
| Cron job セッション | ❌ スキップ |
| Subagent セッション | ❌ スキップ |
| メッセージ2件未満 | ❌ スキップ |

## 2つのモード

起動時に自動検出：

### 拡張モード（holographic メモリプラグイン有効時）
- holographic の SQLite 接続を共有
- `fact_store(action='search')` が wiki 結果を自動含む
- 追加ツール不要

### スタンドアロンモード（holographic なし）
- 独自の SQLite 接続を管理
- `wiki_search` ツールを追加
- 他のメモリプラグインから独立して動作

## 使用方法

```bash
# 全 wiki ページを表示
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM wiki_pages WHERE page_type='session' ORDER BY date DESC"

# キーワード検索
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, summary FROM wiki_pages WHERE title LIKE '%keyword%'"
```

## 機能

- **7言語 i18n**: en/zh/ja/ko/de/fr/es — LLM が会話言語を検出し、同じ言語で wiki ページを生成
- **品質スコアリング**: 1-5段階（5=深く重要、1=ノイズ）
- **トピック分類**: トピックの自動発見と集約ページの維持
- **エンティティ抽出**: 会話から主要なエンティティを識別
- **プロバイダー解決**: Hermes の `PROVIDER_REGISTRY` を使用、ハードコード URL なし
- **グレースフルデグラデーション**: LLM 不利用時はデフォルト分析にフォールバック
- **SQLite 3.31+ 互換**: Python 3.9+ 対応（RETURNING 句不使用）

## トラブルシューティング

**プラグインが読み込まれない？**
- `~/.hermes/config.yaml` の `plugins.enabled` に `hermes-wiki` があるか確認
- ディレクトリが `~/.hermes/plugins/hermes_wiki/`（アンダースコア、ハイフンではない）か確認

**wiki ページが生成されない？**
- LLM 設定を確認：`model.default` と `model.provider`
- ログに `hermes-wiki: LLM failed` がないか確認

## ライセンス

MIT
