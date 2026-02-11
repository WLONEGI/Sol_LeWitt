# Mode-specific Prompting: Comic & Character Sheet

- `comic_page_render`:
  - panel readability, character continuity, dialogue area clarity
- `character_sheet_render`:
  - use style from `story_framework` + identity from `character_sheet`
  - render onto the provided layout template when available

# Character Sheet System Structure (for `character_sheet_render`)
When `mode=character_sheet_render`, enforce this exact design protocol:

## A. Source Priority (fixed)
1) Style/Rendering source: `story_framework`
- Prefer `story_framework.theme`, `story_framework.world_policy`, `story_framework.art_style_policy`.
- Line art / screentone / shading policy must be inherited from `story_framework.art_style_policy` first.

2) Identity source: `character_sheet`
- Prefer `character_profile` then `writer_slide` data.
- Preserve immutable identity traits (face/hair/body/silhouette/accessories).

## B. Template-grounded Placement
If `layout_template_id` is provided, treat template layout as the primary canvas.
- Keep template frame/section structure intact.
- Include all five required content groups: [メインビジュアル, デザイン詳細, 表情集, 三面図, アクションポーズ]

## C. Sheet Layout Contract
- Aspect ratio: respect input `aspect_ratio` (default 2:3 if ambiguous).
- Background: clean white background.
- Color: full color.
- Typography/labels: Only section headings are allowed. No random symbols.

## D. Per-section Requirements
- [メインビジュアル] full-body hero shot.
- [デザイン詳細] close-up callouts for face/hair/accessories/costume motifs.
- [表情集] diverse emotional range with off-model prevention.
- [三面図] front / side / back with consistent proportions.
- [アクションポーズ] 2-4 readable poses.

# Negative Constraints

For `comic_page_render`:
- "panel border break", "unreadable dialogue area", "bad anatomy", "extra limbs", "missing fingers", "deformed hands", "off-model character", "inconsistent costume", "watermark", "signature"

For `character_sheet_render`:
- "extra text artifacts", "inconsistent proportions", "off-model face", "off-model hairstyle", "off-model body", "anatomy distortion", "extra limbs", "missing fingers", "deformed hands", "watermark", "signature", "logo"

# Character Sheet contents skeleton
- [FORMAT_VERSION] CharacterSheet.Unified.v1
- [STYLE_SOURCE] story_framework
- [IDENTITY_SOURCE] character_sheet
- [メインビジュアル] [デザイン詳細] [表情集] [三面図] [アクションポーズ]
- [CONSISTENCY_RULES] immutable face/hair/body/costume anchors
