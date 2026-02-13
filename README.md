# Sol LeWitt: AI Slide with Nano Banana

> **"Hand for the Mind"** — 想像力を形にする、AIマルチエージェント・スライド生成システム。

Sol LeWitt（ソル・ルウィット）は、ユーザーの抽象的なアイデアから、調査、構成案の作成、美しいビジュアルアセットの生成、そして最終的なスライド資料（PPTX）の統合までを一気通貫で自動化するインテリジェント・システムです。

## 🌟 プロジェクトの概要

このプロジェクトは、複数の専門エージェントが協調して動作する **マルチエージェント・ワークフロー** を核としています。

- **想像を現実に**: 箇条書きや断片的なメモから、洗練されたプレゼンスライドを作成。
- **一貫したデザイン**: Imagen を活用した、プロジェクト全体で統一感のある高品質な画像生成。
- **データ駆動**: Web検索とデータ分析による、事実に裏打ちされたコンテンツ作成。

## 🏗️ リポジトリ構造

本プロジェクトは大まかに以下の2つのコンポーネントで構成されています。

### [🎨 Frontend (Next.js)](./frontend)
Vercel AI SDK を活用した、リアルタイムな対話と成果物プレビューを提供するWebインターフェース。
- **技術スタック**: Next.js 15, Tailwind CSS v4, Zustand, Vercel AI SDK.
- **特徴**: 思考プロセスの可視化、スライドのリアルタイムレンダリング、画像編集（In-painting）。

### [⚙️ Backend (Python)](./backend)
LangGraph を用いた高度なエージェント・ワークフロー・エンジン。
- **技術スタック**: LangGraph, FastAPI, Google Vertex AI (Gemini), PostgreSQL, Cloud Storage.
- **特徴**: 自律的なタスク分解、マルチエージェント・オーケストレーション、永続的なステート管理。

## 🚀 はじめに

各ディレクトリの `README.md` を参照してください。

- [バックエンドのセットアップ](./backend/README.md)
- [フロントエンドのセットアップ](./frontend/README.md)

## 📚 ドキュメント

詳細な技術ドキュメントはそれぞれの `docs` ディレクトリにあります。

- [バックエンド・ドキュメント](./backend/docs/README.md)
- [フロントエンド・ドキュメント](./frontend/docs/README.md)

---
© 2026 Sol LeWitt Project Authors.
