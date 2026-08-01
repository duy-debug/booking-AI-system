"""Unit tests for composition-root settings and resource ownership."""

import json
from pathlib import Path
from typing import cast

import httpx
import pytest

import app.dependencies as dependencies
from app.core.config import Settings
from app.dialog.flow_loader import FlowDefinition, FlowLoader


def settings(
    *,
    pos_base_url: str = "http://pos.test",
    pos_timeout_seconds: float = 10.0,
    booking_flow_path: Path | None = None,
    max_auto_transitions: int = 8,
) -> Settings:
    if booking_flow_path is None:
        return Settings(
            pos_base_url=pos_base_url,
            pos_timeout_seconds=pos_timeout_seconds,
            max_auto_transitions=max_auto_transitions,
        )
    return Settings(
        pos_base_url=pos_base_url,
        pos_timeout_seconds=pos_timeout_seconds,
        booking_flow_path=booking_flow_path,
        max_auto_transitions=max_auto_transitions,
    )


@pytest.mark.asyncio
async def test_owned_client_is_closed_idempotently() -> None:
    container = await dependencies.create_application_container(settings())

    assert not container.http_client.is_closed

    await container.close()
    await container.close()

    assert container.http_client.is_closed


@pytest.mark.asyncio
async def test_injected_client_is_not_closed() -> None:
    def unused_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(unused_transport))
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    await container.close()

    assert not client.is_closed
    await client.aclose()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"pos_base_url": "  "}, "base URL"),
        ({"pos_timeout_seconds": 0}, "timeout"),
        ({"pos_timeout_seconds": -1}, "timeout"),
        ({"max_auto_transitions": 0}, "auto transitions"),
        ({"booking_flow_path": Path("missing-flow.json")}, "flow path"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_settings_are_rejected_before_container_creation(
    overrides: dict[str, object],
    message: str,
) -> None:
    defaults = settings()
    invalid = Settings(
        pos_base_url=str(overrides.get("pos_base_url", defaults.pos_base_url)),
        pos_timeout_seconds=cast(
            float,
            overrides.get("pos_timeout_seconds", defaults.pos_timeout_seconds)
        ),
        booking_flow_path=cast(
            Path,
            overrides.get("booking_flow_path", defaults.booking_flow_path),
        ),
        max_auto_transitions=cast(
            int,
            overrides.get("max_auto_transitions", defaults.max_auto_transitions)
        ),
    )
    with pytest.raises(ValueError, match=message):
        await dependencies.create_application_container(invalid)


@pytest.mark.asyncio
async def test_owned_client_is_closed_when_flow_loading_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_flow = tmp_path / "invalid.json"
    invalid_flow.write_text("{", encoding="utf-8")
    client = httpx.AsyncClient()
    monkeypatch.setattr(dependencies.httpx, "AsyncClient", lambda **kwargs: client)

    with pytest.raises(json.JSONDecodeError):
        await dependencies.create_application_container(
            settings(booking_flow_path=invalid_flow)
        )

    assert client.is_closed


@pytest.mark.asyncio
async def test_injected_client_is_not_closed_when_flow_loading_fails(
    tmp_path: Path,
) -> None:
    invalid_flow = tmp_path / "invalid.json"
    invalid_flow.write_text("{", encoding="utf-8")
    client = httpx.AsyncClient()

    with pytest.raises(json.JSONDecodeError):
        await dependencies.create_application_container(
            settings(booking_flow_path=invalid_flow),
            http_client=client,
        )

    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_loads_flow_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    original_load = FlowLoader.load

    def load_spy(path: Path) -> FlowDefinition:
        calls.append(path)
        return original_load(path)

    monkeypatch.setattr(FlowLoader, "load", staticmethod(load_spy))
    client = httpx.AsyncClient()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    assert calls == [settings().booking_flow_path]

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_lifespan_closes_owned_container() -> None:
    async with dependencies.application_container_lifespan(settings()) as container:
        client = container.http_client
        assert not client.is_closed

    assert client.is_closed


@pytest.mark.asyncio
async def test_dependency_getters_return_container_instances() -> None:
    client = httpx.AsyncClient()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    assert dependencies.get_dialog_controller(container) is container.dialog_controller
    assert dependencies.get_memory_cache(container) is container.memory_cache

    await container.close()
    await client.aclose()
