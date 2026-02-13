from src.app.app import (
    _extract_text_and_reasoning_chars_from_chunk,
    _filter_planner_writer_content_for_ui,
)


def test_filter_planner_writer_accepts_reasoning_part() -> None:
    chunk = {
        "content": [
            {"type": "reasoning", "text": "planner thought"},
        ]
    }

    filtered = _filter_planner_writer_content_for_ui(chunk)
    assert filtered == [{"type": "thinking", "text": "planner thought"}]


def test_filter_planner_writer_uses_additional_kwargs_reasoning_fallback() -> None:
    chunk = {
        "content": [{"type": "text", "text": "{\"steps\":[]}"}],
        "additional_kwargs": {"reasoning_content": "internal planner thought"},
    }

    filtered = _filter_planner_writer_content_for_ui(chunk)
    assert filtered == [{"type": "thinking", "thinking": "internal planner thought"}]


def test_extract_text_and_reasoning_counts_reasoning_type() -> None:
    chunk = {
        "content": [
            {"type": "reasoning", "text": "abc"},
            {"type": "text", "text": "xy"},
        ]
    }

    text_chars, reasoning_chars = _extract_text_and_reasoning_chars_from_chunk(chunk)
    assert text_chars == 2
    assert reasoning_chars == 3
