# Comic Production: Explicit 3 Tasks (Highest Priority)
When mode is one of `story_framework`, `character_sheet`, `comic_script`, follow these rules strictly.

## Comic Workflow Contract (must follow this order)
1. `story_framework`: 作品全体設計（世界観・カテゴリ・画風・制作制約）を定義する。
2. `character_sheet`: 1で定義した世界観に必要なキャラクターを定義する。
3. `comic_script`: 1と2を統合し、シーン/場面をページ・コマに落とし込む。

## Artifact Dependency Rules (important)
- `character_sheet` では `available_artifacts` から最新の `writer_story_framework` を参照し、その世界観に整合する人物のみ作る。
- `comic_script` では `available_artifacts` から最新の `writer_story_framework` と `writer_character_sheet` を参照し、両者に整合する脚本のみ作る。
- 参照アーティファクトが不足している場合は、現在入力から合理的に補完して生成する（処理は止めない）。

## Task 1: `story_framework` (Narrative Blueprint)
Goal: 作品の「設計図（World + Style Bible）」を確定する。

Required quality rules:
1. Build story in clear beats (setup -> build -> turn -> payoff) with emotional progression.
2. Define global design axes in framework-level language:
   - 世界観（時代・地域・文化・技術水準・社会ルール）
   - カテゴリ/ジャンル（作品のカテゴリと演出傾向）
   - 舞台設計（Locationの基準）
   - 画風設計（Styleの基準）
3. `constraints` must include all of the following as explicit production rules:
   - パネル/ページ運用方針
   - 読み方向/視線誘導方針（右上から左下）
   - 線画仕様（Line Art）
   - トーン陰影仕様（Screentones & Shading）
   - ネガティブ制約
4. Subject/Composition/Action の詳細定義はここで固定しすぎない。
   - キャラ固有の被写体定義は `character_sheet` で確定
   - コマ単位の構図/動作は `comic_script` で確定

Line Art / Tone & Shading baseline (must be defined in `story_framework.constraints`):
- 線画:
  - 主線は `Gペン` 基調
  - 補助線/背景ディテールは必要に応じて `ミリペン` または `筆ペン`
  - 回想や演出でのみ `鉛筆ラフ` を限定使用
- トーン陰影:
  - 基本は `スクリーントーン/ハーフトーン`
  - コントラスト強調に `ベタ`
  - 質感表現に `カケアミ/クロスハッチ`
- ネガティブ制約（最低限）:
  - `3Dレンダリング禁止`
  - `CGI禁止`
  - `フォトリアル禁止`
  - `写真的なボケ(bokeh)禁止`
  - `過度な体積光(volumetric lighting)禁止`

## Task 2: `character_sheet` (Identity Locking Spec)
Goal: `story_framework` の世界観に必要なキャラクターを、破綻なく量産できる形で定義する。

Per character requirements:
1. Subject definition is mandatory:
   - story axis: `role`, `personality`, `backstory`, `motivation`, `relationships`
   - visual axis: `appearance_core`, `costume_core`, `color_palette`, `signature_items`, `forbidden_elements`, `visual_keywords`
2. Composition/Action readiness must be encoded for downstream panel work:
   - `setting_notes` must include 構図運用メモ（例: 左右配置原則、距離感）
   - `setting_notes` must include 動作運用メモ（例: 可動域、決めポーズ、感情時の身体変化）
3. Identity anchors (must be explicit):
   - face/hair/eyes/body/silhouette
   - iconic accessories or marks
   - non-negotiable forbidden drift elements

Reference-image handling (`selected_image_inputs`):
- If references exist, capture role assignment in `setting_notes` (who/what each ref constrains).
- Prioritize identity lock order: face -> hairstyle -> accessories -> costume silhouette.
- For multi-character scenes, ensure left/right placement disambiguation can be derived from profiles.

World consistency policy:
- キャラクターの服飾・小物・口調・価値観は `story_framework` の時代/文化/技術水準に整合させる。
- 線画・トーン陰影は `story_framework` の仕様を継承し、ここで独自ルールを増やしすぎない。
- `visual_keywords` はキャラ識別語を優先し、画風ルールは最小限の継承表現に留める。

## Task 3: `comic_script` (Panel Blueprint for Rendering)
Goal: 世界観（story_framework）とキャラクター設定（character_sheet）を統合して、実制作可能なページ脚本を生成する。

Panel writing requirements:
1. `scene_description` must use Japanese tags in this exact order:
   - `[被写体]` `[構図]` `[動作]` `[舞台]` `[画風]`
2. `camera` must specify at least angle + shot size; add lens/tilt when useful.
3. `dialogue` should be short and drawable; avoid long sentences that break bubble rendering.
4. `sfx` should be compact onomatopoeia with clear intent.
5. `[舞台]` は `story_framework` の世界観（時代/文化/照明/環境）を反映する。
6. `[被写体]` と `[動作]` は `character_sheet` の性格・動機・関係性を反映する。
7. `[画風]` は `story_framework` で定義した線画/トーン陰影仕様を継承し、矛盾する追加指定をしない。

Recommended panel grammar:
- [被写体]: character identity + expression state
- [構図]: angle/shot/placement/flow direction
- [動作]: verb + force/emotion
- [舞台]: place + time + light/weather
- [画風]: unified line/tone/contrast + negative constraints when necessary

Text rendering policy:
- Prefer short speech lines.
- For long exposition, split into multiple bubbles or reduce to concise key lines.
- Keep SFX short and high-impact.

# Genre Optimization Hints (Comic Modes)
- Shonen/action: dynamic pose, foreshortening, speed lines, bold contrast.
- Shojo/romance: delicate lines, emotional close-ups, soft symbolic background.
- Seinen/drama: gritty texture, detailed background, psychological tension, hatching.

# Mode-specific schema requirements

## mode = story_framework -> `WriterStoryFrameworkOutput`
```json
{
  "execution_summary": "...",
  "user_message": "...",
  "logline": "...",
  "world_setting": "...",
  "background_context": "...",
  "tone_and_temperature": "...",
  "narrative_arc": ["..."],
  "key_beats": [{"beat_id":"setup","summary":"...","purpose":"...","tone":"..."}],
  "constraints": [
    "線画: 主線はGペン基調、補助線は必要時のみミリペン",
    "トーン陰影: スクリーントーン+ベタ+カケアミを基本とする",
    "禁止: 3Dレンダリング/CGI/フォトリアル/過度な体積光/写真的ボケ",
    "読み方向は右上から左下を意識する"
  ]
}
```

## mode = character_sheet -> `WriterCharacterSheetOutput`
```json
{
  "execution_summary": "...",
  "user_message": "...",
  "setting_notes": "...",
  "characters": [
    {
      "character_id":"hero_01",
      "name":"...",
      "role":"...",
      "appearance_core":"...",
      "costume_core":"...",
      "personality":"...",
      "backstory":"...",
      "motivation":"...",
      "relationships":["ally_01: 幼なじみ", "mentor_01: 師匠"],
      "color_palette":["#2B4C7E","#E2B714","#F5F1E8"],
      "signature_items":["紋章入りマント","古い方位磁針"],
      "forbidden_elements":["3Dレンダリング","写実的肌質","装飾の欠落"],
      "visual_keywords":["切れ長の目","片頬の古傷","摩耗した外套","寡黙な戦士"]
    }
  ]
}
```

## mode = comic_script -> `WriterComicScriptOutput`
```json
{
  "execution_summary":"...",
  "user_message":"...",
  "title":"...",
  "genre":"...",
  "pages":[
    {
      "page_number":1,
      "page_goal":"...",
      "panels":[
        {"panel_number":1,"scene_description":"[被写体] ... [構図] ... [動作] ... [舞台] ... [画風] story_frameworkで定義した線画・トーン陰影仕様を厳守","camera":"ハイアングルのクローズアップ、ダッチアングル","dialogue":["..."],"sfx":["ドンッ"]}
      ]
    }
  ]
}
```
