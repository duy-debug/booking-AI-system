# Test fixtures: mock Qdrant, mock Groq, mock httpx

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings as app_settings


@pytest.fixture(scope="session", autouse=True)
def patch_settings():
    app_settings.GROQ_API_KEY = "test-key"
    app_settings.ADMIN_API_KEY = "test-admin-key"
    app_settings.QDRANT_HOST = "localhost"
    app_settings.QDRANT_PORT = 6333
    app_settings.BOOKING_API_URL = "http://test-backend"
    app_settings.BOOKING_API_SERVICE_KEY = "test-service-key"
    yield


@pytest.fixture(scope="session")
def mock_qdrant():
    from app.integrations import qdrant as qdrant_mod

    mock_client = AsyncMock()
    qdrant_mod._client = mock_client
    yield mock_client
    qdrant_mod._client = None


@pytest.fixture(scope="session")
def mock_groq():
    from app.integrations import groq as groq_mod

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Cau tra loi tu AI."))]
    mock_client.chat.completions.create.return_value = mock_response
    groq_mod.get_groq_client.cache_clear()
    with patch.object(groq_mod, "get_groq_client", return_value=mock_client):
        yield mock_client


@pytest.fixture(scope="function")
def client(mock_qdrant, mock_groq):
    # Patch init functions BEFORE app module is loaded
    from unittest.mock import patch

    async def fake_init_qdrant():
        from app.integrations import qdrant as qdrant_mod

        qdrant_mod._client = mock_qdrant
        return mock_qdrant

    async def fake_init_client():
        from app.integrations import booking_api as api_mod

        if api_mod._client is None:
            import httpx

            api_mod._client = httpx.AsyncClient()
        return api_mod._client

    with patch("app.integrations.qdrant.init_qdrant", side_effect=fake_init_qdrant):
        with patch("app.integrations.booking_api.init_client", side_effect=fake_init_client):
            from app.main import app

            with TestClient(app) as c:
                yield c


@pytest.fixture(scope="session")
def auth_headers():
    return {"Authorization": "Bearer test-admin-key"}
