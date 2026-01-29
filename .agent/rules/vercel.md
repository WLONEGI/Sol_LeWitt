---
trigger: model_decision
description: Data Stream Protocolの定義について
---

Data Stream Protocol (Server-Sent Events via JSON)
Event Type (JSON type field)	Example SSE Output	Description
start	data: {"type":"start","messageId":"..."}	メッセージの開始を示します。
text-start	data: {"type":"text-start","id":"..."}	テキストブロックの生成開始。
text-delta	data: {"type":"text-delta","id":"...","delta":"Hello"}	テキストの差分コンテンツ。
text-end	data: {"type":"text-end","id":"..."}	テキストブロックの生成終了。
reasoning-start	data: {"type":"reasoning-start","id":"..."}	推論プロセス（思考）の開始。
reasoning-delta	data: {"type":"reasoning-delta","id":"...","delta":"..."}	推論プロセスの差分内容。
reasoning-end	data: {"type":"reasoning-end","id":"..."}	推論プロセスの終了。
start-step	data: {"type":"start-step"}	ステップ（LLM呼び出し単位）の開始。
finish-step	data: {"type":"finish-step"}	ステップの終了。
tool-input-start	data: {"type":"tool-input-start","toolCallId":"...","toolName":"..."}	ツール呼び出し入力のストリーミング開始。
tool-input-delta	data: {"type":"tool-input-delta","toolCallId":"...","inputTextDelta":"..."}	ツール入力引数の差分。
tool-input-available	data: {"type":"tool-input-available","toolCallId":"...","input":{...}}	ツール入力引数の完成。
tool-output-available	data: {"type":"tool-output-available","toolCallId":"...","output":{...}}	ツール実行結果の返却。
source-url	data: {"type":"source-url","sourceId":"...","url":"..."}	外部URLの参照情報。
source-document	data: {"type":"source-document","sourceId":"...","mediaType":"file","title":"..."}	ドキュメント参照情報。
file	data: {"type":"file","url":"...","mediaType":"image/png"}	生成されたファイル（画像など）への参照。
data-* (Custom)	data: {"type":"data-weather","data":{...}}	任意の構造化データ（data-プレフィックス付きタイプ名）。
error	data: {"type":"error","errorText":"..."}	エラー発生時の通知。
finish	data: {"type":"finish"}	メッセージ全体の生成完了。
[DONE]	data: [DONE]	ストリーム自体の終了（SSE標準マーカー）。
補足:

フロントエンド（DefaultChatTransport）はデフォルトでこのJSON形式をパースします。
バックエンドの sse_formatter.py が実装している 0:text 形式は、このバージョンのデフォルト伝送方式とは異なる可能性があります。相互運用性を確保するためには、バックエンドの実装を上記のJSON形式に合わせるか、フロントエンド側でカスタムTransportを使用する必要があると考えられます。