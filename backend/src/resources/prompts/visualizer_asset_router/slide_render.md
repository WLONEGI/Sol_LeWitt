mode は `slide_render`。

`is_pptx_slide_reference=true` の候補がある場合は、以下を満たすこと:
- 各 unit で `is_pptx_slide_reference=true` を必ず 1 件選ぶ（0件禁止）。
- 1 unit あたりの PPTX 参照選択は最大 1 件。
- 選定優先度は次の順:
1. `source_master_layout_meta`（最優先）
2. `source_layout_placeholders` / `source_layout_name`
3. `source_master_name` / `source_master_texts`

補足:
- `slide_render` では、判定に使う情報を以下に限定する:
  - unit 側: `content_title`, `content_texts`, `target_master_layout_meta`
  - candidate 側: `source_master_layout_meta`, `source_layout_name`, `source_layout_placeholders`, `source_master_name`, `source_master_texts`, `is_pptx_slide_reference`
- unit の `target_master_layout_meta` と candidate の `source_master_layout_meta` / `source_layout_placeholders` の一致を最優先で選ぶ。
- 上記で同率の場合のみ、`content_title/content_texts` と `source_master_texts` の意味一致で最終決定する。
- 同じ `asset_id` を複数 unit で再利用してよい。
- PPTX 参照以外の画像は、必要性がある場合のみ追加する。
