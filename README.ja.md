# hermes-wiki-plugin

[Hermes Agent](https://github.com/NousResearch/hermes-agent) の Karpathy LLM Wiki パターンプラグイン — セッションから wiki ページへの自動変換、品質スコアリング、トピック分類、エンティティ抽出、7言語 i18n 対応。

> 🌐 [English](README.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

## なぜこのプラグインが必要か

Hermesは毎日大量の価値ある会話を生み出します——デバッグ、意思決定の議論、問題解決、アイデアの探求。しかし、この知識には3つの問題があります：

- **セッション終了とともに知識が沈む**。次に類似の問題に直面したとき、「前にこんなことをやった気がする」と思うだけで、詳細を思い出せない。`session_search`で生の会話を検索できるが、ノイズが多く文脈が断片化している。
- **構造化された蓄積がない**。会話はリニアなチャットログであり、トピック・決定・結論別に整理されたドキュメントではない。
- **セッション横断の知識を関連づけられない**。同じトピックが異なるセッションで議論されたり、同じプロジェクトの異なるフェーズがつなげられない。

## このプラグインの機能

セッション終了時に自動的にLLMを呼び、会話を構造化されたwikiページに蒸留します：

- **品質スコアリング**（1-5）：ノイズを自動フィルタリングし、価値あるセッションのみ保持
- **トピック分類 + エンティティ抽出**：「この会話が何についてだったか」を自動識別
- **重要な決定と問題解決**：「何を決定し、なぜ、どのように問題を解決したか」を抽出
- **Fact抽出**：再利用可能な知識（ツールの癖、ハマりどころ、ワークフローの発見）を長期メモリに書き込み、将来の検索で直接ヒット
- **7言語対応**：会話と同じ言語でwikiページを生成

## ユースケース

**日常会話が知識ベースに**
技術的な質問でも、仕事の計画の議論でも、新しいアイデアの探索でも、各会話の終了時に自動的に構造化された要約が生成されます。日を重ねるごとに、wikiはあなたとHermesが共に構築する知識ベースになります。

**トラブルシューティングが痕跡を残す**
エラーの発生、原因の調査、解決策の発見——このプロセスが自動的にwikiページとして結晶化します。次に類似の問題が起きたとき、wikiを検索する方がチャット履歴をスクロールするよりはるかに高速です。

**意思決定の履歴が追跡可能に**
アプローチの議論、選択肢の比較、決定の実行——思考プロセスが自動的にアーカイブされます。後で見直したとき、「なぜこのアプローチを選んだのか」が明確にわかります。

**個人の好みと経験が蓄積**
Fact抽出を通じて、作業習慣、よく使うツール、過去のハマりポイントが長期メモリに自動的に蓄積されます。Hermesを使うほど、あなたをより深く理解するようになります。

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
Hermesと会話する
  → セッション終了（クローズ / トピック切替 / リセット）
    → on_session_end または on_session_reset フック発火（ミリ秒、非ブロッキング）
      → フックがメッセージを渡さない場合、state.dbから読み取り
        → メッセージをSQLiteにキューイング（日付セグメント化）
          → バックグラウンドデーモンスレッド起動
            → 設定済みLLMを呼び出し（config.yamlから）
              → 分析：品質スコア / 言語 / トピック / エンティティ / 意思決定 / facts
              → 構造化wikiページをSQLiteに書き込み（quality >= 4）
              → 再利用可能なfactsをholographic memoryに抽出（拡張モード時）
  → 1時間ごとのバッチスキャン（フックが見逃したものを補足）
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
- ツールは `memory` toolset に登録

## 使用方法

### wiki ページの検索

**スタンドアロンモード**：
```
あなた：nginx に関する議論を wiki で検索
Hermes：[wiki_search(query='nginx') を呼び出し]
  → 一致する wiki ページを返す
```

**ヒント**：LLM が常に `wiki_search` を優先するとは限りません。wiki 結果を確実に得るには、クエリで明示的に「wiki」に言及してください：
```
あなた：wiki_search で nginx に関する議論を検索
あなた：Wiki で今日の活動を検索
あなた：wiki でカスタムエンドポイントの作業を検索
```

複数語クエリに対応 — ツールはクエリを単語に分割し、任意の単語に一致します：
```
あなた：wiki_search で "wiki プラグイン開発" を検索
  → "wiki" または "プラグイン" または "開発" を含むページに一致
```

### 直接的な確認

```bash
# 全 wiki ページを表示
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, quality, date, topics FROM wiki_pages WHERE page_type='session' ORDER BY date DESC"

# キーワード検索
sqlite3 ~/.hermes/memory_store.db \
  "SELECT title, summary FROM wiki_pages WHERE title LIKE '%keyword%'"
```

## 機能

- **7言語i18n**: en/zh/ja/ko/de/fr/es — LLMがセッション言語を検出し、その言語でwikiページを生成
- **品質スコアリング**: 1-5スケール（5=深く重要、1=ノイズ）、低品質セッションは最小限の処理
- **トピック分類**: トピックを自動発見、トピック集約ページとセッションタイムラインを維持
- **エンティティ抽出**: 会話から重要なエンティティ（人物、ツール、システム）を識別
- **Fact抽出**: 再利用可能な知識（ツールの癖、ハマりポイント、個人の好み）をholographic memoryに書き込み、`fact_store`で検索可能
- **デュアルフックトリガー**: `on_session_end`（セッション終了）+ `on_session_reset`（トピック切替）でほぼリアルタイムにwiki生成
- **プロバイダー解決**: Hermesの`PROVIDER_REGISTRY`を使用 — ハードコードURLなし
- **グレースフルデグレード**: LLM利用不可時のデフォルト分析へのフォールバック
- **SQLite 3.31+対応**: Python 3.9+で動作（RETURNING句不使用）

## トラブルシューティング

**プラグインが読み込まれない？**
- `~/.hermes/config.yaml` の `plugins.enabled` に `hermes-wiki` があるか確認
- ディレクトリが `~/.hermes/plugins/hermes_wiki/`（アンダースコア、ハイフンではない）か確認

**wiki ページが生成されない？**
- LLM 設定を確認：`model.default` と `model.provider`
- ログに `hermes-wiki: LLM failed` がないか確認

## ライセンス

MIT
