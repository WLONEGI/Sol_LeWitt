---
name: Gemini AI Integration
description: Procedures for connecting to and verifying Gemini 3.0 via google-genai SDK.
---

# Gemini AI Integration

本プロジェクトでは `google-genai` SDK を使用して Gemini モデルに接続しています。

### 実装のポイント
- **ライブラリ**: `google-genai` (v0.3.0以上)
- **認証**: 環境変数 `VERTEX_PROJECT_ID` と `VERTEX_LOCATION` を使用して `genai.Client(vertexai=True, ...)` を初期化します。
- **コード例**: `src/utils/image_generation.py` などを参照。

### 環境変数
- `VERTEX_PROJECT_ID`: GCP プロジェクト ID
- `VERTEX_LOCATION`: GCP リージョン

### 認証
- `google-genai` は環境変数 `GOOGLE_APPLICATION_CREDENTIALS` を使用して認証します。

### 参考情報
- [google-genai](https://ai.google.dev/gemini-api/docs)
Geminiモデルの機能や実装方法についてはこちらを参照してください。