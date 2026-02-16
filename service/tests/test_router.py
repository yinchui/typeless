from voice_text_organizer.router import route_rewrite


def test_router_fallback_to_local_when_cloud_fails() -> None:
    messages = [{"role": "user", "content": "hello"}]

    def cloud(_messages: list[dict[str, str]]) -> str:
        raise RuntimeError("cloud down")

    def local(_messages: list[dict[str, str]]) -> str:
        return "local result"

    result = route_rewrite(
        messages,
        cloud_fn=cloud,
        local_fn=local,
        default_mode="cloud",
        fallback=True,
    )

    assert result == "local result"


def test_route_rewrite_passes_messages_to_cloud() -> None:
    messages = [{"role": "system", "content": "hi"}, {"role": "user", "content": "test"}]
    called_with: dict[str, list[dict[str, str]]] = {}

    def mock_cloud(msgs: list[dict[str, str]]) -> str:
        called_with["messages"] = msgs
        return "result"

    result = route_rewrite(messages, cloud_fn=mock_cloud, local_fn=lambda _m: "", default_mode="cloud")

    assert result == "result"
    assert called_with["messages"] == messages
