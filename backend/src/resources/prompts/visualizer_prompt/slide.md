# Mode-specific Prompting: Slide

- `slide_render`:
  - Prioritize information density over decorative illustration.
  - Treat each slide as data-anchored communication, not abstract art.
  - Preserve concrete facts from Writer/Research inputs without simplification.
  - Keep explicit hierarchy and text-safe zones.
  - Comparison content: use split/grid composition.

# High-density Content Rules (`slide_render`)
- Use `structured_prompt.contents` to include substantive text content (not short slogans).
- For non-title slides, include:
  - key statements,
  - list items,
  - quantitative findings (numbers, units, years, percentages) when available.
- Prefer explicit formatting that keeps data semantics visible:
  - `指標名: 値 単位 (時点/条件)`,
  - `A vs B: 差分/比率`,
  - `順位. 項目 - 根拠指標`.
- If Writer/Research provides exact numbers or ranges, keep the exact values and units.
- Do not replace concrete values with vague wording (e.g., avoid "many", "large", "significant" when exact values exist).
- Prefer layouts that can hold dense content cleanly:
  - comparison table-like blocks,
  - ranked/bulleted lists,
  - metric cards with labels and values.
- Keep content faithful and compact:
  - no omission of essential bullets,
  - no speculative numeric invention,
  - no decorative filler that displaces core content.

# Readability Constraints (`slide_render`)
- Ensure dense text remains legible: clear grouping, balanced spacing, strong contrast.
- Avoid oversized background motifs that reduce information area.
- Title slide can be lighter, but all other slides should remain content-forward.
- Keep labels attached to values (no unlabeled bars, icons, or shapes).

# Negative Constraints
- "blur", "pixelated", "low resolution", "artifacts", "grainy", "washed out", "distortion", "cropped", "out of frame", "bad composition", "cluttered", "watermark", "signature", "username", "gibberish text", "blurry text", "decorative-only scene", "abstract art without data", "vague unlabeled chart"
