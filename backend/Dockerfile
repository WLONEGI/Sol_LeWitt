# Cloud Runデプロイ用 Dockerfile
# LibreOffice と Poppler (pdf2image) を含むPython環境
# Build: docker build -t ai-slide-backend .
# Run: docker run -p 8080:8080 -e PORT=8080 ai-slide-backend

FROM python:3.12-slim-bookworm

# 環境変数
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# LibreOfficeのホームディレクトリ設定（headless実行時に必要）
ENV HOME=/tmp

# システム依存パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    # LibreOffice (PPTX→PDF変換用)
    libreoffice-impress \
    libreoffice-common \
    # Poppler (PDF→PNG変換用、pdf2imageが使用)
    poppler-utils \
    # PostgreSQL client library
    libpq-dev \
    # 日本語フォント（プレゼン資料の日本語表示用）
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    # ビルドツール（一部Pythonパッケージに必要）
    build-essential \
    # curl (ヘルスチェック等で便利)
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ
WORKDIR /app

# Python依存関係のインストール
COPY pyproject.toml requirements.txt README.md ./

# pipで直接インストール
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir .

# アプリケーションコードをコピー
COPY . .

# 非rootユーザーで実行（セキュリティ）
# Cloud Runはデフォルトでroot以外のユーザーでの実行を推奨
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    # LibreOffice用の一時ディレクトリを作成
    mkdir -p /tmp/.config/libreoffice && \
    chown -R appuser:appuser /tmp/.config

USER appuser

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || python -c "import src.app.app; print('OK')" || exit 1

# Cloud Runは $PORT 環境変数（デフォルト8080）を受け取る
# uvicorn起動時にポートを指定
CMD ["sh", "-c", "python scripts/init_db.py && uvicorn src.app.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
