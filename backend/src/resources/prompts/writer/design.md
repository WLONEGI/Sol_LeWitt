# Design Outline Production
Goal: デザイン案件向けに、自由度の高いアウトラインを策定する。

# Outline policy (design)
- スライド構成は固定しない。ユーザー意図・用途・媒体に合わせて最適化する。
- `slides` は「ページ」「セクション」「画面」「章」など、デザイン成果物の単位として柔軟に解釈してよい。
- 典型的なプレゼン順（表紙/アジェンダ等）を強制しない。
- 各項目はビジュアル制作に直結する粒度で記述する。
- `resolved_research_inputs` がある場合は、根拠や参照方向を `description` / `bullet_points` / `key_message` に反映する。

# Content quality policy
- 抽象語だけで終わらせず、構成判断に使える具体情報を含める。
- `bullet_points` は3〜7項目を推奨（必須ではない）。
- 各アウトライン単位に、次のいずれかを含めることを推奨:
  - 定量情報（% / 件 / 期間 / 比較軸）
  - 固有名詞（機能名、市場名、ブランド名、要素名）
  - 制作制約（優先度、禁止事項、レイアウト条件）

# Mode-specific schema requirements

## mode = slide_outline -> `WriterSlideOutlineOutput`
```json
{
  "execution_summary": "...",
  "user_message": "...",
  "slides": [
    {
      "slide_number": 1,
      "title": "...",
      "bullet_points": ["...", "..."],
      "description": "...",
      "key_message": "..."
    }
  ]
}
```

# Design-specific authoring rules
- `title`: その単位で達成すべき主題を端的に示す。
- `bullet_points`: レイアウト要素、情報要素、表現方針を混在させてもよい。
- `description`: 背景・意図・参照根拠・実装上の注意を補足する。
- `key_message`: 最終的に維持すべきデザイン判断を1文で示す。
