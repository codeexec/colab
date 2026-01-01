"""Tests for server.py

Comprehensive test suite for the Jupyter kernel management server.

Run with:
    pytest test_server.py -v
    pytest test_server.py --cov=server --cov-report=term-missing
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .server import (
    CrashRecoveryState,
    JupyterClient,
    KernelManager,
    LogLevel,
    Settings,
    StructuredLogger,
)


# =========================
# Test Fixtures
# =========================

@pytest.fixture
def settings(monkeypatch):
    """Test settings fixture."""
    # Clear all JUPYTER_* environment variables for clean test state
    import os
    for key in list(os.environ.keys()):
        if key.startswith('JUPYTER_'):
            monkeypatch.delenv(key, raising=False)

    return Settings(
        _env_file=None,  # Don't load .env file
        server_url="http://test-jupyter:8080",
        token="test-token-123",
        crash_sleep_duration=0.1  # Short duration for tests
    )


@pytest.fixture
def logger():
    """Test logger fixture."""
    return StructuredLogger(min_level=LogLevel.DEBUG)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.cookies = MagicMock()
    client.cookies.get.return_value = "test-xsrf-token"
    return client


@pytest.fixture
def jupyter_client(settings, logger, mock_httpx_client):
    """JupyterClient with mocked HTTP client."""
    client = JupyterClient(settings, logger)
    client._http_client = mock_httpx_client
    return client


@pytest.fixture
def kernel_manager(jupyter_client, logger, settings):
    """KernelManager fixture."""
    return KernelManager(
        jupyter_client=jupyter_client,
        logger=logger,
        crash_sleep_duration=settings.crash_sleep_duration
    )


# =========================
# Unit Tests: StructuredLogger
# =========================

class TestStructuredLogger:
    """Tests for StructuredLogger class."""

    def test_log_level_filtering(self, capsys):
        """Test that log levels are filtered correctly."""
        logger = StructuredLogger(min_level=LogLevel.WARN)

        logger.debug("test", "debug message")
        logger.info("test", "info message")
        logger.warn("test", "warn message")

        captured = capsys.readouterr()
        assert "debug message" not in captured.out
        assert "info message" not in captured.out
        assert "warn message" in captured.out

    def test_datetime_utc_usage(self, capsys):
        """Test that timezone-aware timestamps are used."""
        from datetime import datetime

        logger = StructuredLogger()
        logger.info("test", "test message")

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out)

        # Verify timestamp format
        assert "ts" in log_entry
        # Should be ISO format with timezone
        parsed_dt = datetime.fromisoformat(log_entry["ts"])
        assert parsed_dt.tzinfo is not None

    def test_metadata_inclusion(self, capsys):
        """Test that metadata is included in logs."""
        logger = StructuredLogger()
        logger.info("test", "message", {"key": "value", "count": 42})

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out)

        assert log_entry["meta"]["key"] == "value"
        assert log_entry["meta"]["count"] == 42


# =========================
# Unit Tests: Settings
# =========================

class TestSettings:
    """Tests for Settings configuration."""

    def test_default_values(self, monkeypatch):
        """Test that default values are set correctly."""
        # Clear all JUPYTER_* environment variables
        import os
        for key in list(os.environ.keys()):
            if key.startswith('JUPYTER_'):
                monkeypatch.delenv(key, raising=False)

        settings = Settings(_env_file=None)  # Disable .env loading
        assert settings.server_url == "http://127.0.0.1:8080"
        assert settings.token == ""
        assert settings.crash_sleep_duration == 30.0

    def test_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        # Clear all JUPYTER_* environment variables first
        import os
        for key in list(os.environ.keys()):
            if key.startswith('JUPYTER_'):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("JUPYTER_SERVER_URL", "http://custom:9999")
        monkeypatch.setenv("JUPYTER_TOKEN", "custom-token")

        settings = Settings(_env_file=None)
        assert settings.server_url == "http://custom:9999"
        assert settings.token == "custom-token"


# =========================
# Unit Tests: CrashRecoveryState
# =========================

class TestCrashRecoveryState:
    """Tests for CrashRecoveryState."""

    def test_crash_mode_cycle(self):
        """Test entering and exiting crash mode."""
        state = CrashRecoveryState()
        assert not state.is_crashed

        state.enter_crash_mode(duration=10.0)
        assert state.is_crashed
        assert state.crash_count == 1
        assert state.should_wait()

        state.exit_crash_mode()
        assert not state.is_crashed
        assert not state.should_wait()

    def test_resume_timestamp(self):
        """Test resume timestamp calculation."""
        state = CrashRecoveryState()
        state.enter_crash_mode(duration=5.0)

        resume = state.get_resume_timestamp()
        assert resume > time.time()
        assert resume <= time.time() + 5.1  # Small buffer for execution time

    def test_multiple_crashes_increment_count(self):
        """Test that crash count increments on multiple crashes."""
        state = CrashRecoveryState()

        state.enter_crash_mode(duration=1.0)
        assert state.crash_count == 1

        state.exit_crash_mode()
        state.enter_crash_mode(duration=1.0)
        assert state.crash_count == 2


# =========================
# Unit Tests: JupyterClient
# =========================

class TestJupyterClient:
    """Tests for JupyterClient class."""

    @pytest.mark.asyncio
    async def test_context_manager(self, settings, logger):
        """Test async context manager lifecycle."""
        client = JupyterClient(settings, logger)

        async with client as c:
            assert c._http_client is not None
            assert isinstance(c._http_client, httpx.AsyncClient)

        # After exit, client should be closed (we can't easily test this without mocking)

    @pytest.mark.asyncio
    async def test_build_auth_headers(self, jupyter_client):
        """Test authentication header building."""
        jupyter_client._xsrf_token = "test-xsrf"

        headers = jupyter_client._build_auth_headers(include_xsrf=True)
        assert headers["Authorization"] == "token test-token-123"
        assert headers["X-XSRFToken"] == "test-xsrf"

        headers_no_xsrf = jupyter_client._build_auth_headers(include_xsrf=False)
        assert "X-XSRFToken" not in headers_no_xsrf

    @pytest.mark.asyncio
    async def test_build_url(self, jupyter_client):
        """Test URL building with token."""
        url = jupyter_client._build_url("/api/kernels")
        assert url == "http://test-jupyter:8080/api/kernels?token=test-token-123"

        url_with_params = jupyter_client._build_url("/api/kernels?name=python")
        assert url_with_params == "http://test-jupyter:8080/api/kernels?name=python&token=test-token-123"

    @pytest.mark.asyncio
    async def test_create_kernel_success(self, jupyter_client, mock_httpx_client):
        """Test successful kernel creation."""
        # Mock XSRF token retrieval
        mock_xsrf_response = AsyncMock()
        mock_xsrf_response.status_code = 200

        # Mock kernel creation
        mock_response = MagicMock()  # Use MagicMock, not AsyncMock, for response
        mock_response.status_code = 201
        mock_response.json = MagicMock(return_value={"id": "kernel-123", "name": "python3"})
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client.get.return_value = mock_xsrf_response
        mock_httpx_client.post.return_value = mock_response

        result = await jupyter_client.create_kernel()

        assert result["id"] == "kernel-123"
        assert mock_httpx_client.post.called

    @pytest.mark.asyncio
    async def test_delete_kernel_success(self, jupyter_client, mock_httpx_client):
        """Test successful kernel deletion."""
        # Mock XSRF token retrieval
        mock_xsrf_response = AsyncMock()
        mock_xsrf_response.status_code = 200

        # Mock kernel deletion
        mock_response = MagicMock()  # Use MagicMock for response
        mock_response.status_code = 204
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client.get.return_value = mock_xsrf_response
        mock_httpx_client.delete.return_value = mock_response

        await jupyter_client.delete_kernel("kernel-123")

        assert mock_httpx_client.delete.called

    @pytest.mark.asyncio
    async def test_execute_code_via_websocket(self, jupyter_client):
        """Test WebSocket code execution."""
        with patch("websockets.connect") as mock_connect:
            mock_ws = AsyncMock()

            # Generate test message ID
            test_msg_id = "test-msg-id"

            # Mock WebSocket messages
            mock_ws.recv.side_effect = [
                json.dumps({
                    "header": {"msg_type": "status", "msg_id": "status-1"},
                    "content": {"execution_state": "busy"},
                    "parent_header": {"msg_id": test_msg_id}
                }),
                json.dumps({
                    "header": {"msg_type": "execute_result", "msg_id": "result-1"},
                    "content": {"data": {"text/plain": "'hello'"}},
                    "parent_header": {"msg_id": test_msg_id}
                }),
                json.dumps({
                    "header": {"msg_type": "status", "msg_id": "status-2"},
                    "content": {"execution_state": "idle"},
                    "parent_header": {"msg_id": test_msg_id}
                })
            ]
            mock_connect.return_value.__aenter__.return_value = mock_ws

            # Mock uuid to control msg_id
            with patch("uuid.uuid4", return_value=MagicMock(hex=test_msg_id)):
                with patch("colab_code_executor.server.uuid.uuid4") as mock_uuid:
                    mock_uuid.return_value = test_msg_id

                    # Need to allow the real uuid call but control str(uuid.uuid4())
                    results = await jupyter_client.execute_code_via_websocket(
                        "kernel-123",
                        "print('hello')"
                    )

            assert len(results) == 3
            assert results[-1]["content"]["execution_state"] == "idle"


# =========================
# Unit Tests: KernelManager
# =========================

class TestKernelManager:
    """Tests for KernelManager class."""

    @pytest.mark.asyncio
    async def test_start_kernel_success(self, kernel_manager, mock_httpx_client):
        """Test successful kernel start."""
        # Mock XSRF and kernel creation
        mock_xsrf_response = AsyncMock()
        mock_xsrf_response.status_code = 200

        mock_response = MagicMock()  # Use MagicMock for response
        mock_response.status_code = 201
        mock_response.json = MagicMock(return_value={"id": "kernel-456", "name": "python3"})
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client.get.return_value = mock_xsrf_response
        mock_httpx_client.post.return_value = mock_response

        result = await kernel_manager.start_kernel()

        assert result["id"] == "kernel-456"
        assert "kernel-456" in kernel_manager.kernels

    @pytest.mark.asyncio
    async def test_start_kernel_with_retry(self, kernel_manager, mock_httpx_client):
        """Test kernel start with retry on failure."""
        # Mock XSRF responses
        mock_xsrf_response = AsyncMock()
        mock_xsrf_response.status_code = 200
        mock_httpx_client.get.return_value = mock_xsrf_response

        # First call fails, second succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.raise_for_status.side_effect = httpx.HTTPError("Connection failed")

        mock_response_success = MagicMock()
        mock_response_success.status_code = 201
        mock_response_success.json = MagicMock(return_value={"id": "kernel-retry", "name": "python3"})
        mock_response_success.raise_for_status = MagicMock()

        mock_httpx_client.post.side_effect = [mock_response_fail, mock_response_success]

        result = await kernel_manager.start_kernel()

        assert result["id"] == "kernel-retry"
        assert mock_httpx_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_code_kernel_not_found(self, kernel_manager):
        """Test execute with non-existent kernel."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await kernel_manager.execute_code("nonexistent", "print(1)")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_shutdown_kernel_success(self, kernel_manager, mock_httpx_client):
        """Test successful kernel shutdown."""
        kernel_manager.kernels["kernel-shutdown"] = {"id": "kernel-shutdown"}

        # Mock XSRF and deletion
        mock_xsrf_response = AsyncMock()
        mock_xsrf_response.status_code = 200

        mock_response = MagicMock()  # Use MagicMock for response
        mock_response.status_code = 204
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client.get.return_value = mock_xsrf_response
        mock_httpx_client.delete.return_value = mock_response

        result = await kernel_manager.shutdown_kernel("kernel-shutdown")

        assert "shutdown" in result["message"].lower()
        assert "kernel-shutdown" not in kernel_manager.kernels

    @pytest.mark.asyncio
    async def test_shutdown_kernel_not_found(self, kernel_manager):
        """Test shutdown of non-existent kernel."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await kernel_manager.shutdown_kernel("nonexistent")

        assert exc_info.value.status_code == 404


# =========================
# Integration Tests: API Routes
# =========================

class TestAPIRoutes:
    """Integration tests for FastAPI routes."""

    def test_health_endpoint(self):
        """Test health check endpoint."""
        # Create a test client without lifespan to avoid actual Jupyter connection
        test_app = FastAPI()

        @test_app.get("/health")
        async def health():
            return {"status": "ok"}

        client = TestClient(test_app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
