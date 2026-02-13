mode は `slide_render`。

`is_pptx_slide_reference=true` の候補がある場合は、以下を満たすこと:
- 各 unit で `is_pptx_slide_reference=true` を必ず 1 件選ぶ（0件禁止）。
- 1 unit あたりの PPTX 参照選択は最大 1 件。
- 選定優先度は次の順:
1. `source_master_layout_meta`（最優先）
2. `source_texts`

補足:
- 同じ `asset_id` を複数 unit で再利用してよい。
- PPTX 参照以外の画像は、必要性がある場合のみ追加する。
