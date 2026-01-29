import pytest
from unittest.mock import AsyncMock, patch
from src.core.workflow.callbacks import StreamingThoughtCallbackHandler

@pytest.mark.asyncio
async def test_streaming_thought_callback():
    handler = StreamingThoughtCallbackHandler()
    
    with patch("src.core.workflow.callbacks.adispatch_custom_event", new_callable=AsyncMock) as mock_dispatch:
        await handler.on_llm_new_token("hello")
        
        mock_dispatch.assert_called_once_with("thought", {"token": "hello"})
        
    with patch("src.core.workflow.callbacks.adispatch_custom_event", new_callable=AsyncMock) as mock_dispatch:
        await handler.on_llm_new_token("")
        
        mock_dispatch.assert_not_called()
