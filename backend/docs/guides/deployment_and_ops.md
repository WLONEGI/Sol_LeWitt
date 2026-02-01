# デプロイ & 運用ガイド

## 1. Docker ビルド
Cloud Run へのデプロイを前提としています。`libreoffice` や日本語フォントを含むベースイメージを使用します。

```bash
docker build -t ai-slide-backend .
```

## 2. Google Cloud デプロイ (Cloud Run)
`cloudbuild.yaml` を使用して自動ビルド・デプロイを行います。

```bash
gcloud builds submit --config cloudbuild.yaml .
```

### Cloud Run 設定の要点
- **メモリ**: 2GB 以上推奨 (PPTX 解析/画像生成の並列処理のため)
- **CPU**: 2 以上推奨
- **Cloud SQL 接続**: インスタンス接続を有効にする必要があります。

## 3. モニタリング
- **Cloud Logging**: エージェントの推論ログ、Worker のエラーを詳細に出力。
- **LangSmith (オプション)**: 開発時に `LANGCHAIN_TRACING_V2=true` を設定することで、グラフ実行の詳細をトレース可能。
