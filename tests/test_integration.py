"""
Core of Potato v1.0.0 — Integration Test Suite
"""
import pytest

pytestmark = pytest.mark.asyncio

# ─── HEALTH & STATUS ────────────────────────────────────────

class TestHealthAndStatus:
    """Test server health and status endpoints."""

    async def test_health_returns_200(self, client):
        """GET /api/health returns 200 with ok status."""
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"

    async def test_status_requires_auth(self, client):
        """GET /api/status returns 401 without auth token."""
        resp = await client.get("/api/status")
        assert resp.status == 401

    async def test_status_returns_uptime_with_auth(self, client):
        """GET /api/status returns uptime and job count with valid token."""
        resp = await client.get(
            "/api/status",
            headers={"X-Admin-Token": "test-secret-token"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert "uptime_seconds" in data
        assert "jobs_today" in data


# ─── CHAT COMPLETIONS (BLOCKING) ────────────────────────────

class TestChatCompletionsBlocking:
    """Test POST /v1/chat/completions in non-streaming mode."""

    async def test_basic_completion(self, client):
        """Valid request returns OpenAI-format response."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Hello, world!"}],
                "user": "OCtest",
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert len(data["choices"][0]["message"]["content"]) > 0

    async def test_completion_with_auth_header(self, client):
        """NaModu key via Authorization: Bearer header."""
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer CDheph"},
            json={
                "model": "gemini",
                "messages": [{"role": "user", "content": "Test"}],
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["choices"][0]["message"]["content"]

    async def test_completion_with_x_user_header(self, client):
        """NaModu key via X-User header."""
        resp = await client.post(
            "/v1/chat/completions",
            headers={"X-User": "OCorac"},
            json={
                "model": "chatgpt",
                "messages": [{"role": "user", "content": "Test"}],
            },
        )
        assert resp.status == 200

    async def test_model_alias_gpt(self, client):
        """Model 'gpt' should alias to ChatGPT."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt",
                "messages": [{"role": "user", "content": "Test"}],
                "user": "OCtest",
            },
        )
        assert resp.status == 200

    async def test_response_has_usage_field(self, client):
        """Response includes usage with token counts."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Token test"}],
                "user": "OCtest",
            },
        )
        data = await resp.json()
        assert "usage" in data
        assert "prompt_tokens" in data["usage"]
        assert "completion_tokens" in data["usage"]
        assert "total_tokens" in data["usage"]


# ─── CHAT COMPLETIONS (STREAMING / SSE) ─────────────────────

class TestChatCompletionsStreaming:
    """Test POST /v1/chat/completions with stream=true (SSE)."""

    async def test_streaming_returns_sse(self, client):
        """Streaming request returns text/event-stream."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Stream test"}],
                "user": "OCtest",
                "stream": True,
            },
        )
        assert resp.status == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")

        body = await resp.text()
        assert "data:" in body
        assert "[DONE]" in body


# ─── SESSION ISOLATION (NaModu) ──────────────────────────────

class TestSessionIsolation:
    """Test that different NaModu keys create isolated sessions."""

    async def test_different_keys_get_different_job_ids(self, client):
        """Two different NaModu keys produce distinct job IDs."""
        resp1 = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Session A"}],
                "user": "OCtest",
            },
        )
        data1 = await resp1.json()

        resp2 = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Session B"}],
                "user": "CDheph",
            },
        )
        data2 = await resp2.json()

        assert data1["id"] != data2["id"]

    async def test_same_key_reuses_session(self, client):
        """Same NaModu key + model reuses the conversation URL."""
        resp1 = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "First"}],
                "user": "OCtest",
            },
        )
        assert resp1.status == 200

        server = client.app["_server"]
        url = server.storage.get_url_by_key("OCtest_grok")
        assert url is not None


# ─── INPUT VALIDATION ────────────────────────────────────────

class TestInputValidation:
    """Test request validation and error handling."""

    async def test_missing_user_returns_error(self, client):
        """Request without user identification returns 400."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Test"}],
            },
        )
        assert resp.status == 400

    async def test_invalid_user_format(self, client):
        """User key too short/long or invalid chars."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Test"}],
                "user": "X",  # Too short
            },
        )
        assert resp.status == 400

    async def test_unknown_caller_prefix(self, client):
        """User key with unregistered 2-char prefix."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Test"}],
                "user": "ZZtest",  # 'ZZ' not in caller_map
            },
        )
        assert resp.status == 400

    async def test_missing_messages_returns_error(self, client):
        """Request without messages array."""
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "grok", "user": "OCtest"},
        )
        assert resp.status == 400

    async def test_invalid_model_returns_error(self, client):
        """Request with unrecognized model name."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "nonexistent-model",
                "messages": [{"role": "user", "content": "Test"}],
                "user": "OCtest",
            },
        )
        assert resp.status == 400

    async def test_browser_not_running_returns_500(self, client):
        """Request when browser manager is stopped returns 500."""
        server = client.app["_server"]
        await server.browser.stop()
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "grok",
                "messages": [{"role": "user", "content": "Test"}],
                "user": "OCtest",
            },
        )
        assert resp.status == 500
        await server.browser.start()  # Restore


# ─── ADMIN ENDPOINTS ────────────────────────────────────────

class TestAdminEndpoints:
    """Test admin API endpoints with authentication."""

    async def test_admin_requires_token(self, client):
        """Admin endpoints reject requests without token and from non-same-origin."""
        resp = await client.post("/api/logs/clear")
        assert resp.status == 401

    async def test_admin_accepts_valid_token(self, client):
        """Admin endpoints accept valid X-Admin-Token."""
        resp = await client.post(
            "/api/logs/clear",
            headers={"X-Admin-Token": "test-secret-token"},
        )
        assert resp.status == 200

    async def test_caller_map_get_requires_auth(self, client):
        """GET /api/caller-map without token returns 401."""
        resp = await client.get("/api/caller-map")
        assert resp.status == 401

    async def test_caller_map_get_with_token(self, client):
        """GET /api/caller-map with valid token returns 200."""
        resp = await client.get(
            "/api/caller-map",
            headers={"X-Admin-Token": "test-secret-token"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert "OC" in data

    async def test_default_urls_get_requires_auth(self, client):
        """GET /api/default-urls without token returns 401."""
        resp = await client.get("/api/default-urls")
        assert resp.status == 401

    async def test_default_urls_get_with_token(self, client):
        """GET /api/default-urls with valid token returns 200."""
        resp = await client.get(
            "/api/default-urls",
            headers={"X-Admin-Token": "test-secret-token"}
        )
        assert resp.status == 200
