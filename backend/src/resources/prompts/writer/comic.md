# Comic Production: Explicit 3 Tasks (Highest Priority)
When mode is one of `story_framework`, `character_sheet`, `comic_script`, follow these rules strictly.
Each mode must return its own JSON schema independently. Do not mix fields across the three schemas.

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
1. `story_framework` object only. Do not output legacy top-level fields like `logline` or `constraints`.
2. Include exactly the 9 core policy areas:
   - concept
   - theme
   - format_policy
   - structure_type
   - arc_overview
   - core_conflict
   - world_policy
   - direction_policy
   - art_style_policy
3. `direction_policy` must explicitly define:
   - paneling_policy
   - eye_guidance_policy（右上から左下の流れ）
   - page_turn_policy
   - dialogue_policy
4. `art_style_policy` must explicitly define:
   - line_style
   - shading_style
   - negative_constraints
5. Subject/Composition/Action の詳細定義はここで固定しすぎない。
   - キャラ固有の被写体定義は `character_sheet` で確定
   - コマ単位の構図/動作は `comic_script` で確定

Line Art / Tone & Shading baseline (must be defined in `story_framework.art_style_policy`):
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
1. Keep output minimal and explicit. Do not output turnaround/expression/pose specs in this mode.
2. Required identity fields:
   - `character_id`
   - `name`
   - `story_role`
   - `core_personality`
   - `motivation`
   - `weakness_or_fear`
   - `silhouette_signature`
   - `face_hair_anchors`
   - `costume_anchors`
   - `color_palette` (`main/sub/accent`)
   - `signature_items`
   - `forbidden_drift`
3. Optional field:
   - `speech_style`
4. Identity anchors must be explicit and reusable across scenes.

Reference-image handling (`selected_image_inputs`):
- If references exist, reflect them directly in `face_hair_anchors`, `costume_anchors`, and `silhouette_signature`.
- Prioritize identity lock order: face -> hairstyle -> accessories -> costume silhouette.

World consistency policy:
- キャラクターの服飾・小物・口調・価値観は `story_framework.world_policy` に整合させる。
- 線画・トーン陰影は `story_framework.art_style_policy` を継承し、ここで独自ルールを増やしすぎない。
- `forbidden_drift` はオフモデル防止に使える具体語で定義する。

## Task 3: `comic_script` (Panel Blueprint for Rendering)
Goal: 世界観（story_framework）とキャラクター設定（character_sheet）を統合して、実制作可能なページ脚本を生成する。

Panel writing requirements:
1. `comic_script` はページ/コマ詳細のみを返す。全体制約は `story_framework` で定義済みとして扱う。
2. Do not output global fields such as `title`, `genre`, `theme`, `style bible`, `page_goal`.
3. Each panel must include only these keys:
   - `foreground`
   - `background`
   - `composition`
   - `camera`
   - `lighting`
   - `dialogue`
   - `negative_constraints`
4. `background` は `story_framework.world_policy`（時代/文化/環境）に整合させる。
5. `foreground` と `dialogue` は `character_sheet` の性格・動機・関係性に整合させる。
6. `negative_constraints` は `story_framework.art_style_policy.negative_constraints` を継承し、必要最小限の追加のみ行う。
7. `camera` は angle + shot size を最低限含め、必要時のみ lens/tilt を追加する。
8. `lighting` は時間帯/光源/コントラストを短く具体化する。

Text rendering policy:
- Prefer short speech lines.
- For long exposition, split into multiple bubbles or reduce to concise key lines.

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
  "story_framework": {
    "concept": "...",
    "theme": "...",
    "format_policy": {
      "series_type": "oneshot",
      "medium": "digital",
      "page_budget": {"min": 24, "max": 32},
      "reading_direction": "rtl"
    },
    "structure_type": "kishotenketsu",
    "arc_overview": [
      {"phase":"起","purpose":"導入とフック提示"},
      {"phase":"承","purpose":"対立の拡大"},
      {"phase":"転","purpose":"反転と危機"},
      {"phase":"結","purpose":"決着と余韻"}
    ],
    "core_conflict": "...",
    "world_policy": {
      "era": "...",
      "primary_locations": ["..."],
      "social_rules": ["..."]
    },
    "direction_policy": {
      "paneling_policy": "...",
      "eye_guidance_policy": "右上から左下へ視線誘導",
      "page_turn_policy": "...",
      "dialogue_policy": "1フキダシ1情報を基本とする"
    },
    "art_style_policy": {
      "line_style": "主線はGペン基調",
      "shading_style": "スクリーントーン+ベタ+カケアミ",
      "negative_constraints": ["3Dレンダリング禁止", "フォトリアル禁止"]
    }
  }
}
```

## mode = character_sheet -> `WriterCharacterSheetOutput`
```json
{
  "execution_summary": "...",
  "user_message": "...",
  "characters": [
    {
      "character_id":"hero_01",
      "name":"...",
      "story_role":"...",
      "core_personality":"...",
      "motivation":"...",
      "weakness_or_fear":"...",
      "silhouette_signature":"...",
      "face_hair_anchors":"...",
      "costume_anchors":"...",
      "color_palette":{"main":"#2B4C7E","sub":"#E2B714","accent":"#F5F1E8"},
      "signature_items":["紋章入りマント","古い方位磁針"],
      "forbidden_drift":["髪分け目変更禁止","装飾欠落禁止","フォトリアル肌質禁止"],
      "speech_style":"簡潔で断定的"
    }
  ]
}
```

## mode = comic_script -> `WriterComicScriptOutput`
```json
{
  "execution_summary":"...",
  "user_message":"...",
  "pages":[
    {
      "page_number":1,
      "panels":[
        {
          "panel_number":1,
          "foreground":"主人公が壊れた懐中時計を握りしめる",
          "background":"薄明の機械都市路地、蒸気と配管",
          "composition":"右上から左下へ視線誘導する対角線構図。主人公は手前1/3。",
          "camera":"ローアングルのミディアムショット、35mm",
          "lighting":"朝の斜光。逆光気味で輪郭にハイライト。",
          "dialogue":["これが最後のチャンスだ。"],
          "negative_constraints":["フォトリアル禁止","3Dレンダリング禁止","衣装シルエット改変禁止"]
        }
      ]
    }
  ]
}
```

## Few-shot References (Mode-specific)
Use these as structural adaptation examples from canonical manga genres.
Never copy original proper nouns, exact scene composition, or dialogue from source works.

### few-shot: `story_framework`

#### Example SF-1 (Sports Team Arc)
Reference axis: `SLAM DUNK`, `ハイキュー!!`, `ダイヤのA`

```json
{
  "execution_summary": "スポーツ群像の設計方針を定義した。",
  "user_message": "試合の緊張と成長曲線を両立するフレームを作成した。",
  "story_framework": {
    "concept": "弱小チームが戦術再編で強豪に挑む成長劇",
    "theme": "継続と連携",
    "format_policy": {"series_type":"serialized","medium":"digital","page_budget":{"min":18,"max":22},"reading_direction":"rtl"},
    "structure_type": "three_act",
    "arc_overview": [
      {"phase":"導入","purpose":"欠点の可視化"},
      {"phase":"拡大","purpose":"連携訓練と失敗"},
      {"phase":"反転","purpose":"主力不在で戦術転換"},
      {"phase":"収束","purpose":"新戦術で接戦を成立"}
    ],
    "core_conflict": "個人能力依存と組織戦術重視の対立",
    "world_policy": {"era":"現代","primary_locations":["高校体育館","地区大会会場"],"social_rules":["練習時間制限","学業優先"]},
    "direction_policy": {"paneling_policy":"通常局面は中コマ、決定局面は大ゴマ","eye_guidance_policy":"ボール移動方向で視線誘導","page_turn_policy":"攻守反転でめくりを作る","dialogue_policy":"戦術語を短文化"},
    "art_style_policy": {"line_style":"Gペン主線、速度線強め","shading_style":"トーン控えめ、決定点でベタ","negative_constraints":["フォトリアル禁止","3Dレンダリング禁止"]}
  }
}
```

#### Example SF-2 (Dark Fantasy Quest)
Reference axis: `ベルセルク`, `鋼の錬金術師`, `ダンジョン飯`

```json
{
  "execution_summary": "ダークファンタジーの方針を定義した。",
  "user_message": "倫理対立と旅路を両立する設計にした。",
  "story_framework": {
    "concept": "禁忌知識を巡る巡礼と再建の物語",
    "theme": "代償と責任",
    "format_policy": {"series_type":"serialized","medium":"print","page_budget":{"min":24,"max":30},"reading_direction":"rtl"},
    "structure_type": "jo_ha_kyu",
    "arc_overview": [
      {"phase":"序","purpose":"喪失の提示"},
      {"phase":"破","purpose":"価値観の衝突"},
      {"phase":"急","purpose":"真相開示と選択"}
    ],
    "core_conflict": "秩序維持のための犠牲容認と人命優先の対立",
    "world_policy": {"era":"中世相当","primary_locations":["辺境都市","地下遺構"],"social_rules":["術式登録制","移動許可制"]},
    "direction_policy": {"paneling_policy":"会話は中コマ連続、異形出現で大ゴマ","eye_guidance_policy":"光源と視線で誘導","page_turn_policy":"真相提示直前で止める","dialogue_policy":"専門語は短注釈化"},
    "art_style_policy": {"line_style":"Gペン主線+背景ミリペン","shading_style":"トーン+ハッチング","negative_constraints":["CGI禁止","写真的ボケ禁止","過度な体積光禁止"]}
  }
}
```

#### Example SF-3 (Psychological Suspense)
Reference axis: `MONSTER`, `DEATH NOTE`, `PLUTO`

```json
{
  "execution_summary": "心理サスペンスの基盤を定義した。",
  "user_message": "情報戦と倫理ジレンマを主軸に設計した。",
  "story_framework": {
    "concept": "連続事件の真相を追う調査劇",
    "theme": "正義の相対性",
    "format_policy": {"series_type":"serialized","medium":"digital","page_budget":{"min":20,"max":24},"reading_direction":"rtl"},
    "structure_type": "kishotenketsu",
    "arc_overview": [
      {"phase":"起","purpose":"単発事件として着手"},
      {"phase":"承","purpose":"共通符号の発見"},
      {"phase":"転","purpose":"内部裏切りの露見"},
      {"phase":"結","purpose":"真犯人像の反転"}
    ],
    "core_conflict": "法手続順守と被害抑止の越権行為の衝突",
    "world_policy": {"era":"近未来","primary_locations":["研究機関","再開発地区"],"social_rules":["監視記録常時保存","データ階層アクセス"]},
    "direction_policy": {"paneling_policy":"証拠提示は分割、心理反転は縦長","eye_guidance_policy":"証拠配置順で誘導","page_turn_policy":"証拠開示1コマ前でめくり","dialogue_policy":"推理は短文積み上げ"},
    "art_style_policy": {"line_style":"硬質な主線","shading_style":"低照度ベタ多用","negative_constraints":["フォトリアル禁止","水彩ぼかし禁止"]}
  }
}
```

### few-shot: `character_sheet`

#### Example CS-1 (Action Protagonist)
Reference axis: `ONE PIECE`, `HUNTER×HUNTER`, `NARUTO`

```json
{
  "execution_summary":"アクション主人公の識別軸を定義した。",
  "user_message":"シルエットと口調の再現性を固定した。",
  "characters":[
    {
      "character_id":"lead_01",
      "name":"主人公A",
      "story_role":"主人公",
      "core_personality":"前向きで即断型",
      "motivation":"失われた記録の回収",
      "weakness_or_fear":"仲間の損失への恐れ",
      "silhouette_signature":"短丈上衣+長い布アクセント+重めの靴",
      "face_hair_anchors":"太眉、跳ねた前髪、頬の小さな傷",
      "costume_anchors":"濃色ジャケット、金属バックル、革手袋",
      "color_palette":{"main":"#1F3A5F","sub":"#C17A2A","accent":"#E7E2D9"},
      "signature_items":["方位磁針","記録手帳"],
      "forbidden_drift":["前髪方向変更禁止","布アクセ欠落禁止","フォトリアル肌質禁止"],
      "speech_style":"短文断定"
    }
  ]
}
```

#### Example CS-2 (Slice-of-life Heroine)
Reference axis: `3月のライオン`, `ハチミツとクローバー`, `NANA`

```json
{
  "execution_summary":"日常ドラマ主人公の識別軸を定義した。",
  "user_message":"感情変化を表現しやすい固定要素を整理した。",
  "characters":[
    {
      "character_id":"heroine_01",
      "name":"主人公B",
      "story_role":"主人公",
      "core_personality":"共感的で内省的",
      "motivation":"自分の企画を成立させる",
      "weakness_or_fear":"拒絶に対する萎縮",
      "silhouette_signature":"大きめカーディガン+トート+やや猫背",
      "face_hair_anchors":"下がり目、低い位置のお団子髪",
      "costume_anchors":"生成りカーディガン、細いネックレス、黒スニーカー",
      "color_palette":{"main":"#C7B8A3","sub":"#4F5A6B","accent":"#D86A6A"},
      "signature_items":["付箋付きノート"],
      "forbidden_drift":["髪型長髪化禁止","濃いメイク禁止","常時直立姿勢禁止"],
      "speech_style":"丁寧語中心"
    }
  ]
}
```

#### Example CS-3 (Cyberpunk Antagonist)
Reference axis: `AKIRA`, `攻殻機動隊`, `BLAME!`

```json
{
  "execution_summary":"SF対立者の識別軸を定義した。",
  "user_message":"機械要素の固定点を明確化した。",
  "characters":[
    {
      "character_id":"antagonist_01",
      "name":"対立者C",
      "story_role":"敵対者",
      "core_personality":"冷静で観察志向",
      "motivation":"隠蔽情報の公開",
      "weakness_or_fear":"記憶欠損の進行",
      "silhouette_signature":"長身+片腕義肢+背面ケーブル",
      "face_hair_anchors":"片目インプラント、後ろ流し短髪",
      "costume_anchors":"黒コート、胸部端子、耐電グローブ",
      "color_palette":{"main":"#11161E","sub":"#4A6A8A","accent":"#9BE7FF"},
      "signature_items":["認証キー","折りたたみ端末"],
      "forbidden_drift":["インプラント欠落禁止","義肢左右反転禁止","過度な鏡面反射禁止"],
      "speech_style":"主語省略の短文"
    }
  ]
}
```

### few-shot: `comic_script`

#### Example SC-1 (Sports Finale Page)
Reference axis: `SLAM DUNK`, `あしたのジョー`, `ハイキュー!!`

```json
{
  "execution_summary":"試合終盤の1ページ設計を作成した。",
  "user_message":"運動方向と緊張上昇を読みやすくした。",
  "pages":[
    {
      "page_number":7,
      "panels":[
        {
          "panel_number":1,
          "foreground":"エースが踏み切りから得点動作へ入る",
          "background":"満員スタンドと応援幕",
          "composition":"左下から右上へ対角線、守備者を中景で重ねる",
          "camera":"ローアングルのワイドショット、28mm",
          "lighting":"天井白色光、汗に小ハイライト",
          "dialogue":["ここで決める。","流れを渡さない。"],
          "negative_constraints":["フォトリアル禁止","過度なモーションブラー禁止","観客顔崩れ禁止"]
        }
      ]
    }
  ]
}
```

#### Example SC-2 (Suspense Interrogation Page)
Reference axis: `MONSTER`, `DEATH NOTE`, `寄生獣`

```json
{
  "execution_summary":"尋問シーンの1ページ設計を作成した。",
  "user_message":"違和感の提示点を視線誘導で強調した。",
  "pages":[
    {
      "page_number":12,
      "panels":[
        {
          "panel_number":3,
          "foreground":"調査官が端末を差し出し、被疑者の反応を読む",
          "background":"窓のない取調室、録音ランプのみ点灯",
          "composition":"机を水平軸に上下対置、端末を手前強調",
          "camera":"アイレベルのミディアムクローズアップ、50mm",
          "lighting":"上部蛍光灯の硬い単一光源、深い影",
          "dialogue":["この時刻の行動を説明して。","沈黙の理由は何だ。"],
          "negative_constraints":["過度な残虐表現禁止","フォトリアル肌質禁止","文字化けUI禁止"]
        }
      ]
    }
  ]
}
```

#### Example SC-3 (Daily Comedy Page)
Reference axis: `よつばと!`, `ちびまる子ちゃん`, `クレヨンしんちゃん`

```json
{
  "execution_summary":"日常コメディの1ページ設計を作成した。",
  "user_message":"小ネタ連打が読みやすい配置にした。",
  "pages":[
    {
      "page_number":3,
      "panels":[
        {
          "panel_number":2,
          "foreground":"子どもが大きな買い物袋を抱えてふらつく",
          "background":"夕方の商店街",
          "composition":"主人公中央、左右にリアクション余白",
          "camera":"ややハイアングルのミディアムショット、35mm",
          "lighting":"夕方の暖色自然光、柔らかい影",
          "dialogue":["重いって聞いてない！","中身、お菓子だけだろ。"],
          "negative_constraints":["説教調モノローグ禁止","過度なパース歪み禁止","フォトリアル禁止"]
        }
      ]
    }
  ]
}
```
