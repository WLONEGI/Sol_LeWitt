# 開発者ガイド

## 1. 開発環境の準備
1. **Node.js**: 20.x 以上を推奨。
2. **依存関係のインストール**:
   ```bash
   npm install
   ```
3. **開発サーバーの起動**:
   ```bash
   npm run dev
   ```

## 2. コーディング規約
- **TypeScript**: `any` の使用を避け、インターフェースを定義すること。
- **Tailwind CSS**: スタイルは可能な限り Tailwind クラスで行い、複雑なロジックはコンポーネント外部の `utils` または `hooks` に切り出す。
- **Icons**: Lucide React を使用。

## 3. コンポーネント追加のフロー
1. **Atomic Components**: `src/components/ui/` (shadcn/ui) を優先的に使用。
2. **Feature Components**: 各機能ディレクトリ (`src/features/chat/components/` 等) に作成。
3. **State**: 状態が必要な場合は Zustand ストアへの追加を検討。

## 4. テスト
- **Unit Test**: `npm test` を使用して、フックやユーティリティのロジックを検証します。
- **Test Locations**: 各ソースファイルと同じディレクトリの `__tests__/` フォルダ内に配置。

## 5. UI/UX のベストプラクティス
- **Loading UI**: 非同期処理を伴うコンポーネントには、スケルトンローダー (`Skeleton` コンポーネント) を実装すること。
- **Animations**: `framer-motion` を使用して、リストの追加やパネルの開閉にスムーズな遷移を追加すること。
