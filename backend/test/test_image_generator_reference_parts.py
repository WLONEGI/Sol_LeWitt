from types import SimpleNamespace

from google.genai import types

from src.domain.designer import generator


def _build_success_response() -> SimpleNamespace:
    inline_part = SimpleNamespace(inline_data=SimpleNamespace(data=b"generated-image"))
    candidate = SimpleNamespace(
        finish_reason=types.FinishReason.STOP,
        content=SimpleNamespace(parts=[inline_part]),
        thought_signature=None,
    )
    return SimpleNamespace(candidates=[candidate])


def test_generate_image_uses_file_uri_for_dict_gcs_reference(monkeypatch) -> None:
    response = _build_success_response()
    captured: dict[str, object] = {}
    from_uri_calls: list[dict[str, str | None]] = []

    def fake_generate_content(*, model, contents, config):  # type: ignore[no-untyped-def]
        captured["model"] = model
        captured["contents"] = contents
        captured["config"] = config
        return response

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))

    def fake_from_uri(*, file_uri: str, mime_type: str | None = None, media_resolution=None):  # type: ignore[no-untyped-def]
        from_uri_calls.append({"file_uri": file_uri, "mime_type": mime_type})
        return {"kind": "uri", "file_uri": file_uri, "mime_type": mime_type}

    def fake_from_bytes(*, data: bytes, mime_type: str):  # type: ignore[no-untyped-def]
        return {"kind": "bytes", "len": len(data), "mime_type": mime_type}

    monkeypatch.setattr(generator, "_get_client", lambda: fake_client)
    monkeypatch.setattr(generator.types.Part, "from_uri", fake_from_uri)
    monkeypatch.setattr(generator.types.Part, "from_bytes", fake_from_bytes)
    monkeypatch.setattr(generator.settings, "VL_MODEL", "gemini-test-image-model", raising=False)

    image, thought_signature = generator.generate_image(
        prompt="inpaint this area",
        reference_image={"uri": "gs://demo-bucket/ref-style.webp", "mime_type": "image/webp"},
    )

    assert image == b"generated-image"
    assert thought_signature is None
    assert captured["model"] == "gemini-test-image-model"
    assert len(from_uri_calls) == 1
    assert from_uri_calls[0]["file_uri"] == "gs://demo-bucket/ref-style.webp"
    assert from_uri_calls[0]["mime_type"] == "image/webp"


def test_generate_image_uses_file_uri_for_string_gcs_reference(monkeypatch) -> None:
    response = _build_success_response()
    from_uri_calls: list[dict[str, str | None]] = []

    def fake_generate_content(*, model, contents, config):  # type: ignore[no-untyped-def]
        return response

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))

    def fake_from_uri(*, file_uri: str, mime_type: str | None = None, media_resolution=None):  # type: ignore[no-untyped-def]
        from_uri_calls.append({"file_uri": file_uri, "mime_type": mime_type})
        return {"kind": "uri", "file_uri": file_uri, "mime_type": mime_type}

    monkeypatch.setattr(generator, "_get_client", lambda: fake_client)
    monkeypatch.setattr(generator.types.Part, "from_uri", fake_from_uri)
    monkeypatch.setattr(generator.settings, "VL_MODEL", "gemini-test-image-model", raising=False)

    image, thought_signature = generator.generate_image(
        prompt="inpaint this area",
        reference_image="gs://demo-bucket/ref-source.jpg",
    )

    assert image == b"generated-image"
    assert thought_signature is None
    assert len(from_uri_calls) == 1
    assert from_uri_calls[0]["file_uri"] == "gs://demo-bucket/ref-source.jpg"
    assert from_uri_calls[0]["mime_type"] == "image/jpeg"
