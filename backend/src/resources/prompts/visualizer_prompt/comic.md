# Mode-specific Prompting: Comic & Character Sheet

- `comic_page_render`:
  - panel readability, character continuity, dialogue area clarity
- `character_sheet_render`:
  - build prompt from Writer character information and style policy as-is
  - include only the minimum labels needed for readability
  - if `layout_template_id` is provided, follow the template geometry without adding custom section headers

# Character Sheet System Structure (for `character_sheet_render`)
When `mode=character_sheet_render`, prioritize these sources:

## A. Source Priority (fixed)
1) Style/Rendering source: `story_framework`
- Prefer `story_framework.theme`, `story_framework.world_policy`, `story_framework.art_style_policy`.
- Line art / screentone / shading policy must be inherited from `story_framework.art_style_policy` first.

2) Identity source: `character_sheet`
- Prefer `character_profile` then `writer_slide` data.
- Preserve immutable identity traits (face/hair/body/silhouette/accessories).
- Prioritize these identity keys when available:
  - `silhouette_signature`
  - `face_hair_anchors`
  - `costume_anchors`
  - `forbidden_drift`

## B. Rendering Contract
- Background: clean white background.
- Color: full color.
- Typography/labels: avoid decorative text and random symbols.
- Do not add fixed section tags such as `[Sections]` or custom layout labels not present in Writer output/template.

# Negative Constraints

For `comic_page_render`:
- "panel border break", "unreadable dialogue area", "bad anatomy", "extra limbs", "missing fingers", "deformed hands", "off-model character", "inconsistent costume", "watermark", "signature"

For `character_sheet_render`:
- "extra text artifacts", "inconsistent proportions", "off-model face", "off-model hairstyle", "off-model body", "anatomy distortion", "extra limbs", "missing fingers", "deformed hands", "watermark", "signature", "logo"
