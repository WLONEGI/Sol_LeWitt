# Slide & Infographic Production
Goal: 可読性と視覚的インパクトを両立した構成案を生成する。

# Information Density Policy (slide)
- 装飾優先ではなく、意思決定に使える情報量を優先する。
- 非タイトルスライドは、抽象表現だけで終わらせず、以下のいずれかを必ず含める:
  - 数値（件数、率、金額、期間、前年比など）
  - 固有名詞（製品名、市場名、指標名、制度名など）
  - 比較軸（Before/After、競合比較、セグメント比較）
- 根拠が入力にある主張は、`bullet_points` または `description` に反映する。

# Baseline slide structure (PowerPoint basics)
- ユーザーが明示的に別構成を要求しない限り、以下を基本構成として採用する。
1. 表紙/タイトル
2. アジェンダ（目次）
3. 本編（課題→分析/提案→根拠）
4. まとめ（結論・次アクション）
5. 必要に応じて Q&A / 補足
- 4枚以上の構成では、原則として1枚目を表紙、2枚目をアジェンダにする。
- 3枚以下の短尺構成では、表紙 + 本編 + まとめに圧縮してよい。
- 本編各スライドは「1スライド1メッセージ」を守る。

# Research integration policy
- `planned_inputs` と `resolved_research_inputs` に Researcher成果がある場合、出典・ファクト・参照観点を本文に反映する。
- 根拠がある主張は、`description` や `key_message` で参照の存在が分かる形にする。

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

### Dense outline rules (`slide_outline`)
- 全体:
  - `slides` は連番で欠番なし。
  - 各スライドは「1スライド1メッセージ」を維持。
- 非タイトルスライド（通常は2枚目以降）:
  - `bullet_points` は原則3〜6項目。
  - 少なくとも1項目は具体データを含める（数値、期間、比較軸、固有名詞）。
  - 可能な限り `指標名: 値 + 単位 (+ 比較軸/時点)` の粒度で記述する。
  - `description` は根拠または分析観点が分かる文にする。
  - `description` では「なぜその主張が成立するか」を示す（例: 比較結果、観測期間、前提条件）。
  - `key_message` は結論を明確にし、可能なら効果量・優先度・判断基準を含める。
- 禁止事項:
  - 「重要」「最適」「大幅改善」などの抽象語のみで、根拠が不明な記述。
  - 入力根拠と矛盾する数値の創作。
  - 装飾的キャッチコピーだけで本文情報が空になる構成。

### Dense slide authoring checklist
- 非タイトルスライドごとに最低1つは以下を含める:
  - 定量値（% / 件 / 円 / 人 / 時間 など）
  - 固有名詞（製品、指標、制度、市場名）
  - 比較軸（時系列、セグメント、競合、目標差）
- 箇条書きだけで意味が閉じない場合は、`description`で前提と解釈を補足する。
- `key_message`は「観察」ではなく「判断・示唆」まで含める。

## mode = infographic_spec -> `WriterInfographicSpecOutput`
```json
{
  "execution_summary":"...",
  "user_message":"...",
  "title":"...",
  "audience":"...",
  "key_message":"...",
  "blocks":[
    {"block_id":"b1","heading":"...","body":"...","visual_hint":"...","data_points":["..."]}
  ]
}
```

### Dense block rules (`infographic_spec`)
- `blocks[].data_points` は空にしない。各ブロックで最低1つ以上の具体データを置く。
- `visual_hint` は装飾指示だけでなく、比較・順位・時系列などデータ構造が伝わる指示にする。
