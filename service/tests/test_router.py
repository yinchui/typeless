from voice_text_organizer.router import route_rewrite


def test_router_fallback_to_local_when_cloud_fails() -> None:
    def cloud(_prompt: str) -> str:
        raise RuntimeError("cloud down")

    def local(_prompt: str) -> str:
        return "local result"

    result = route_rewrite(
        "hello",
        cloud_fn=cloud,
        local_fn=local,
        default_mode="cloud",
        fallback=True,
    )

    assert result == "local result"
