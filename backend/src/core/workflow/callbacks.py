from typing import Any, Dict, List, Union
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.outputs import LLMResult

class StreamingThoughtCallbackHandler(AsyncCallbackHandler):
    """
    Callback handler that streams LLM tokens as custom 'thought' events.
    Used to provide real-time updates (Stream of Thought) to the UI.
    """
    
    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Run on new LLM token. Only available when streaming is enabled."""
        if token:
            await adispatch_custom_event("thought", {"token": token})
