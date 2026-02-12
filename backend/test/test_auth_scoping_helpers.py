from fastapi import HTTPException

from src.app.app import _build_graph_config, _extract_uid, _is_protected_path


def test_build_graph_config_includes_user_namespace() -> None:
    config = _build_graph_config("thread-123", "uid-abc")
    assert config["configurable"]["thread_id"] == "thread-123"
    assert config["configurable"]["checkpoint_ns"] == "uid-abc"
    assert config["configurable"]["user_uid"] == "uid-abc"


def test_extract_uid_accepts_firebase_uid_fields() -> None:
    assert _extract_uid({"uid": "u1"}) == "u1"
    assert _extract_uid({"user_id": "u2"}) == "u2"
    assert _extract_uid({"sub": "u3"}) == "u3"


def test_extract_uid_raises_for_invalid_payload() -> None:
    try:
        _extract_uid({})
        raise AssertionError("Expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_is_protected_path_matches_history_threads_chat() -> None:
    assert _is_protected_path("/api/history")
    assert _is_protected_path("/api/threads/abc/snapshot")
    assert _is_protected_path("/api/chat/stream_events")
    assert _is_protected_path("/api/files/upload")
    assert _is_protected_path("/api/image/demo/inpaint")
    assert _is_protected_path("/api/slide-deck/deck-1/slides/2/inpaint")
    assert not _is_protected_path("/health")
