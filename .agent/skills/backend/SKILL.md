---
name: Backend Local Development
description: Procedures for starting and verifying the Python FastAPI backend locally.
---

# Backend Local Development

バックエンドは Python (FastAPI / LangGraph) で構築されています。

## 起動手順

1.  `backend/langgraph` ディレクトリに移動します。
    ```bash
    cd backend/langgraph
    ```
2.  仮想環境を作成・有効化します。
    > **Note:** プロジェクトは `uv` で管理されています。
    ```bash
    # 仮想環境の作成 (Python 3.12)
    uv venv --python 3.12
    
    # 仮想環境の有効化 (Mac/Linux)
    source .venv/bin/activate
    ```

3.  依存関係をインストール・同期します。
    ```bash
    uv sync
    ```

4.  **Database Connection (Cloud SQL Proxy)**:
    ローカル開発では、GCP上のCloud SQLに接続するためにProxyが必要です。
    別のターミナルで以下を実行してください（インスタンス接続名は環境に合わせて変更）：
    ```bash
    ./cloud-sql-proxy aerobic-stream-483505-a0:asia-northeast1:langgraph-pg-core
    ```

5.  サーバーを起動します。
    ```bash
    # 仮想環境内であれば uv run は省略可能ですが、付けておくと確実です
    uv run uvicorn src.api.app:app --reload --port 8000
    ```
6.  [http://localhost:8000/health](http://localhost:8000/health) にアクセスし、`{"status": "ok"}` が返ることを確認します。
