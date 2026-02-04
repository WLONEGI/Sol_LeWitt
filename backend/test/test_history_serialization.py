import pytest
from langchain_core.messages import AIMessage, HumanMessage

# Mock the logic found in app.py to test it in isolation before integration
def serialize_message(msg):
    role = "user"
    if msg.type == "ai":
        role = "assistant"
    elif msg.type == "human":
        role = "user"
    elif msg.type == "system":
        role = "system"
    elif msg.type == "tool":
        return None
    
    content = msg.content
    parts = []
    
    # 1. Handle List Content (already structured)
    if isinstance(content, list):
        text_parts = []
        for c in content:
            if "text" in c:
                text_parts.append(c["text"])
                parts.append({"type": "text", "text": c["text"]})
            # Map other LangChain types if necessary, e.g. image_url
            
        content = "".join(text_parts)
    
    # 2. Handle String Content (flat)
    elif isinstance(content, str):
        parts.append({"type": "text", "text": content})
    
    # 3. Handle Reasoning in additional_kwargs (Gemini/LangChain pattern)
    additional_kwargs = msg.additional_kwargs or {}
    reasoning = additional_kwargs.get("reasoning_content")
    
    if reasoning:
        # Prepend reasoning part
        parts.insert(0, {"type": "reasoning", "reasoning": reasoning})

    return {
        "role": role,
        "content": content,
        "parts": parts, # <--- New Field
        "id": getattr(msg, "id", None)
    }

def test_serialize_simple_message():
    msg = HumanMessage(content="Hello")
    result = serialize_message(msg)
    
    assert result["role"] == "user"
    assert result["content"] == "Hello"
    assert result["parts"] == [{"type": "text", "text": "Hello"}]

def test_serialize_message_with_reasoning():
    msg = AIMessage(
        content="Final Answer",
        additional_kwargs={"reasoning_content": "Thinking process..."}
    )
    result = serialize_message(msg)
    
    assert result["role"] == "assistant"
    # Content remains flat string for compatibility
    assert result["content"] == "Final Answer" 
    # Parts contain structured data
    assert len(result["parts"]) == 2
    assert result["parts"][0] == {"type": "reasoning", "reasoning": "Thinking process..."}
    assert result["parts"][1] == {"type": "text", "text": "Final Answer"}

def test_serialize_structured_list_content():
    # Simulation of a complex message content from LangChain
    msg = AIMessage(content=[
        {"type": "text", "text": "Part 1"},
        {"type": "text", "text": "Part 2"}
    ])
    result = serialize_message(msg)
    
    assert result["content"] == "Part 1Part 2"
    assert len(result["parts"]) == 2
    assert result["parts"] == [
        {"type": "text", "text": "Part 1"},
        {"type": "text", "text": "Part 2"}
    ]

if __name__ == "__main__":
    # Allow running directly for quick check
    test_serialize_simple_message()
    test_serialize_message_with_reasoning()
    test_serialize_structured_list_content()
    print("All serialization tests passed!")
