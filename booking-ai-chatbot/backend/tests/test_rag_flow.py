# Integration tests cho RAG module — KB seed + search + chat API
# Adapt tu booking-ai-system-be

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestKB:
    def test_kb_stats_with_auth(self, client: TestClient, auth_headers: dict, mock_qdrant):
        # Mock count_chunks tra ve >0
        mock_qdrant.get_collection.return_value.points_count = 5
        r = client.get("/api/kb/stats", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total_chunks"] == 5

    def test_kb_seed_without_auth(self, client: TestClient):
        r = client.post("/api/kb/seed")
        assert r.status_code == 401

    def test_kb_seed_with_auth_succeeds(self, client: TestClient, auth_headers: dict, mock_qdrant):
        with patch("app.rag.router.seed_all_docs") as mock_seed:
            mock_seed.return_value = {"seeded_files": {"test.md": 3}, "total_chunks": 3}
            r = client.post("/api/kb/seed", headers=auth_headers)
            assert r.status_code == 200
            assert r.json()["stats"]["total_chunks"] == 3

    def test_kb_stats_without_auth(self, client: TestClient):
        r = client.get("/api/kb/stats")
        assert r.status_code == 401

    def test_chat_valid(self, client: TestClient, mock_qdrant):
        # Mock Qdrant search tra ve chunks
        mock_qdrant.search.return_value = [
            MagicMock(id="1", payload={"source": "test.md", "content": "Noi dung mau"}, score=0.9)
        ]
        r = client.post("/api/chat", json={"query": "xin chao"})
        assert r.status_code == 200
        assert "Cau tra loi" in r.json()["answer"]

    def test_chat_uses_context(self, client: TestClient, mock_qdrant):
        mock_qdrant.search.return_value = [
            MagicMock(id="1", payload={"source": "test.md", "content": "A" * 1000}, score=0.9)
        ]
        with patch("app.rag.chain.get_groq_client") as mock_groq:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
            mock_client.chat.completions.create.return_value = mock_response
            mock_groq.return_value = mock_client

            r = client.post("/api/chat", json={"query": "quy trinh dat booking the nao?"})
            assert r.status_code == 200

            call_kwargs = mock_client.chat.completions.create.call_args
            assert call_kwargs is not None
            messages = call_kwargs[1].get("messages", [])
            system_msg = next(m for m in messages if m["role"] == "system")
            assert len(system_msg["content"]) > 500
