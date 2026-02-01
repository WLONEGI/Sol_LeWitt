from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.callbacks.manager import adispatch_custom_event

class StreamingThoughtCallbackHandler(AsyncCallbackHandler):
    """
    A callback handler that dispatches LLM tokens as custom 'thought' events.
    Used for streaming reasoning/thought processes to the frontend.
    """
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            await adispatch_custom_event("thought", {"token": token})
