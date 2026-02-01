---
trigger: model_decision
description: テスト・検証用スクリプト作成時・検証、サーバー起動時のルール
---

検証スクリプトはtestフォルダ配下に作成すること

サーバ起動する際,既存プロセスが残っている場合は既存プロセスを停止してから起動して。
特にブラウザテスト（Playwright等）の実行前には、`backend/scripts/restart_services.sh` を使用して全プロセスを再起動すること。