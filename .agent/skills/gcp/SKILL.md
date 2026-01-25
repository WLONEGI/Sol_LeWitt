---
name: GCP Cloud SQL Connection
description: Procedures for connecting to GCP Cloud SQL (PostgreSQL) locally using cloud-sql-proxy.
---

# GCP Cloud SQL Connection

GCP上の Cloud SQL (PostgreSQL) にローカルから接続するには、`cloud-sql-proxy` を使用するのが一般的です。

## 接続手順

1.  **Cloud SQL Proxy の準備**:
    `backend/langgraph` ディレクトリに `cloud-sql-proxy` バイナリがあることを確認します（なければダウンロード）。

2.  **Proxy の起動**:
    別のターミナルを開き、以下のコマンドで Proxy を起動します。
    `<INSTANCE_CONNECTION_NAME>` は GCP コンソールの Cloud SQL 概要ページから取得してください（例: `project-id:region:instance-name`）。
    ```bash
    cd backend/langgraph
    ./cloud-sql-proxy <INSTANCE_CONNECTION_NAME>
    ```

3.  **環境変数の設定**:
    `.env` ファイルの `POSTGRES_DB_URI` を、ローカルを経由するように設定します。
    ```ini
    # Proxy経由の場合 (ポート5432を使用)
    POSTGRES_DB_URI=postgresql+psycopg://<DB_USER>:<DB_PASS>@127.0.0.1:5432/<DB_NAME>
    ```

