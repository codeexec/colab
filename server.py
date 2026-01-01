"""FastAPI server for remote Jupyter kernel management.

This server acts as a proxy to a remote Jupyter server, providing endpoints for:
- Starting kernels
- Executing code on kernels via WebSocket
- Shutting down kernels

Features modern Python best practices including:
- Pydantic Settings for configuration
- Structured logging with timezone-aware timestamps
- Async context managers for resource management
- Comprehensive type hints (PEP 604 union syntax)
- Crash recovery with retry logic
- StrEnum for type-safe enumerations
"""

import asyncio
import json
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any
import uvicorn    


try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        """String enumeration for Python 3.10 compatibility."""
        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# =========================
# Config Layer
# =========================

class LogLevel(StrEnum):
    """Structured log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Application configuration with environment variable support.

    All settings can be overridden via environment variables with JUPYTER_ prefix.
    Example: JUPYTER_SERVER_URL=http://localhost:8888
    """
    model_config = SettingsConfigDict(
        env_prefix="JUPYTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    server_url: str = "http://127.0.0.1:8080"
    token: str = ""
    timeout_connect: float = 10.0
    timeout_total: float = 30.0
    crash_sleep_duration: float = 30.0
    log_level: LogLevel = LogLevel.INFO


# =========================
# Logger Layer
# =========================

class StructuredLogger:
    """Structured JSON logger with consistent formatting.

    Produces JSON logs with timestamp, level, scope, message, and optional metadata.
    Uses timezone-aware timestamps via datetime.now(timezone.utc).
    """

    def __init__(self, min_level: LogLevel = LogLevel.INFO):
        self.min_level = min_level
        self._level_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARN: 2,
            LogLevel.ERROR: 3,
        }

    def _should_log(self, level: LogLevel) -> bool:
        """Check if message should be logged based on min_level."""
        return self._level_order[level] >= self._level_order[self.min_level]

    def _log(self, level: LogLevel, scope: str, message: str, meta: dict[str, Any] | None = None) -> None:
        """Internal log method."""
        if not self._should_log(level):
            return

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),  # timezone.utc for Python 3.10+ compatibility
            "level": level.value,
            "scope": scope,
            "message": message,
        }
        if meta:
            entry["meta"] = meta
        print(json.dumps(entry), flush=True)

    def debug(self, scope: str, message: str, meta: dict[str, Any] | None = None) -> None:
        """Log debug message."""
        self._log(LogLevel.DEBUG, scope, message, meta)

    def info(self, scope: str, message: str, meta: dict[str, Any] | None = None) -> None:
        """Log info message."""
        self._log(LogLevel.INFO, scope, message, meta)

    def warn(self, scope: str, message: str, meta: dict[str, Any] | None = None) -> None:
        """Log warning message."""
        self._log(LogLevel.WARN, scope, message, meta)

    def error(self, scope: str, message: str, meta: dict[str, Any] | None = None) -> None:
        """Log error message."""
        self._log(LogLevel.ERROR, scope, message, meta)


# =========================
# Communication Layer
# =========================

class JupyterClient:
    """Client for communicating with remote Jupyter server.

    Handles HTTP and WebSocket communication, XSRF token management,
    and authentication. Uses async context manager for proper cleanup.

    Example:
        async with JupyterClient(settings, logger) as client:
            kernel_info = await client.create_kernel()
            results = await client.execute_code_via_websocket(kernel_info["id"], "print('hello')")
            await client.delete_kernel(kernel_info["id"])
    """

    def __init__(self, settings: Settings, logger: StructuredLogger):
        self.settings = settings
        self.logger = logger
        self._http_client: httpx.AsyncClient | None = None
        self._xsrf_token: str = ""

    async def __aenter__(self) -> "JupyterClient":
        """Async context manager entry."""
        self._http_client = httpx.AsyncClient(
            cookies={},
            timeout=httpx.Timeout(
                self.settings.timeout_total,
                connect=self.settings.timeout_connect
            )
        )
        self.logger.info("jupyter_client", "HTTP client initialized")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._http_client:
            await self._http_client.aclose()
            self.logger.info("jupyter_client", "HTTP client closed")

    async def _get_xsrf_token(self) -> str:
        """Get XSRF token from Jupyter server.

        Makes a GET request to /lab to obtain XSRF cookie required for POST/DELETE.
        Caches token for subsequent requests.

        Returns:
            XSRF token string

        Raises:
            httpx.HTTPError: If token retrieval fails
        """
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        headers = {}
        if self.settings.token:
            headers["Authorization"] = f"token {self.settings.token}"

        # Make a GET request to /lab to get the XSRF cookie
        url = f"{self.settings.server_url}/lab"
        if self.settings.token:
            url = f"{url}?token={self.settings.token}"

        self.logger.debug("get_xsrf_token", f"Attempting to connect to: {url}")
        response = await self._http_client.get(url, headers=headers, follow_redirects=True)
        self.logger.debug("get_xsrf_token", f"Successfully connected, status: {response.status_code}")

        # Extract XSRF token from cookies
        self.logger.debug("get_xsrf_token", f"All cookies: {dict(self._http_client.cookies)}")
        self._xsrf_token = self._http_client.cookies.get("_xsrf", "")
        self.logger.debug("get_xsrf_token", f"Extracted XSRF token: {self._xsrf_token[:20] if self._xsrf_token else 'EMPTY'}")
        return self._xsrf_token

    def _build_auth_headers(self, include_xsrf: bool = False) -> dict[str, str]:
        """Build authentication headers.

        Args:
            include_xsrf: Whether to include XSRF token

        Returns:
            Dictionary of headers
        """
        headers = {}
        if self.settings.token:
            headers["Authorization"] = f"token {self.settings.token}"
        if include_xsrf and self._xsrf_token:
            headers["X-XSRFToken"] = self._xsrf_token
        return headers

    def _build_url(self, path: str) -> str:
        """Build full URL with optional token parameter.

        Args:
            path: API path (e.g., "/api/kernels")

        Returns:
            Full URL with token if configured
        """
        url = f"{self.settings.server_url}{path}"
        if self.settings.token and "?" not in path:
            url = f"{url}?token={self.settings.token}"
        elif self.settings.token:
            url = f"{url}&token={self.settings.token}"
        return url

    async def create_kernel(self) -> dict[str, Any]:
        """Create new kernel on remote Jupyter server.

        Returns:
            Kernel info dictionary with 'id' field

        Raises:
            httpx.HTTPError: If kernel creation fails
        """
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        # Get XSRF token
        xsrf_token = await self._get_xsrf_token()

        # Create kernel
        headers = self._build_auth_headers(include_xsrf=True)
        self.logger.debug("create_kernel", f"Request headers: {headers}")
        response = await self._http_client.post(
            self._build_url("/api/kernels"),
            headers=headers,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()

    async def delete_kernel(self, kernel_id: str) -> None:
        """Delete kernel on remote Jupyter server.

        Args:
            kernel_id: Kernel ID to delete

        Raises:
            httpx.HTTPError: If deletion fails
        """
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        xsrf_token = await self._get_xsrf_token()
        response = await self._http_client.delete(
            self._build_url(f"/api/kernels/{kernel_id}"),
            headers=self._build_auth_headers(include_xsrf=True),
            timeout=10.0
        )
        response.raise_for_status()

    async def execute_code_via_websocket(
        self,
        kernel_id: str,
        code: str,
        timeout: float = 60.0
    ) -> list[dict[str, Any]]:
        """Execute code on kernel via WebSocket.

        Args:
            kernel_id: Target kernel ID
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            List of Jupyter protocol messages

        Raises:
            websockets.WebSocketException: If WebSocket communication fails
            asyncio.TimeoutError: If execution exceeds timeout
        """
        # Build websocket URL
        ws_url = self.settings.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/kernels/{kernel_id}/channels"
        if self.settings.token:
            ws_url = f"{ws_url}?token={self.settings.token}"

        results = []
        msg_id = str(uuid.uuid4())

        # Create execute_request message
        execute_msg = {
            "header": {
                "msg_id": msg_id,
                "username": "",
                "session": str(uuid.uuid4()),
                "msg_type": "execute_request",
                "version": "5.3"
            },
            "parent_header": {},
            "metadata": {},
            "content": {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True
            },
            "buffers": [],
            "channel": "shell"
        }

        async with websockets.connect(ws_url) as ws:
            # Send execute request
            await ws.send(json.dumps(execute_msg))

            # Collect messages until execution is complete
            while True:
                msg_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(msg_raw)

                results.append(msg)

                # Check if execution is complete
                if msg.get("header", {}).get("msg_type") == "status":
                    if msg.get("content", {}).get("execution_state") == "idle":
                        if msg.get("parent_header", {}).get("msg_id") == msg_id:
                            break

        return results


# =========================
# Management Layer
# =========================

@dataclass
class CrashRecoveryState:
    """Tracks crash recovery state for resilience.

    Attributes:
        is_crashed: Whether system is in crashed state
        sleep_until: Timestamp when recovery sleep ends
        crash_count: Number of consecutive crashes (for metrics)
    """
    is_crashed: bool = False
    sleep_until: float = 0.0
    crash_count: int = 0

    def enter_crash_mode(self, duration: float) -> None:
        """Enter crash recovery mode.

        Args:
            duration: Sleep duration in seconds
        """
        self.is_crashed = True
        self.sleep_until = time.time() + duration
        self.crash_count += 1

    def exit_crash_mode(self) -> None:
        """Exit crash recovery mode."""
        self.is_crashed = False
        self.sleep_until = 0.0

    def should_wait(self) -> bool:
        """Check if should wait for crash recovery."""
        return self.is_crashed and time.time() < self.sleep_until

    def get_resume_timestamp(self) -> float:
        """Get timestamp when recovery completes."""
        return self.sleep_until


def with_retry(max_retries: int = 1, delay: float = 30.0):
    """Decorator for automatic retry with delay.

    Args:
        max_retries: Maximum retry attempts
        delay: Delay between retries in seconds

    Usage:
        @with_retry(max_retries=1, delay=30.0)
        async def my_func():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                    else:
                        raise last_exception
        return wrapper
    return decorator


class KernelManager:
    """Manages kernel lifecycle with crash recovery.

    Tracks active kernels and coordinates with JupyterClient for
    creation/execution/deletion. Implements crash recovery with retry logic.

    Attributes:
        kernels: Dictionary mapping kernel_id -> kernel_info
        crash_recovery: Crash recovery state tracker
    """

    def __init__(
        self,
        jupyter_client: JupyterClient,
        logger: StructuredLogger,
        crash_sleep_duration: float = 30.0
    ):
        self.client = jupyter_client
        self.logger = logger
        self.crash_sleep_duration = crash_sleep_duration
        self.kernels: dict[str, dict[str, Any]] = {}
        self.crash_recovery = CrashRecoveryState()

    async def _wait_for_crash_recovery(self, scope: str) -> None:
        """Wait if system is in crash recovery mode.

        Args:
            scope: Logging scope for context
        """
        if self.crash_recovery.should_wait():
            resume_at = datetime.fromtimestamp(
                self.crash_recovery.get_resume_timestamp(),
                tz=timezone.utc
            )
            self.logger.warn(
                scope,
                "Crash flag active, waiting",
                {"resumeAt": resume_at.isoformat()}
            )
            delay = max(0, self.crash_recovery.sleep_until - time.time())
            await asyncio.sleep(delay)

    @with_retry(max_retries=1, delay=30.0)
    async def start_kernel(self) -> dict[str, str]:
        """Start new kernel with automatic retry.

        Uses @with_retry decorator to eliminate manual retry logic.
        Checks crash recovery state before proceeding.

        Returns:
            Dictionary with kernel 'id'

        Raises:
            HTTPException: If kernel start fails after retry
        """
        await self._wait_for_crash_recovery("start_kernel")

        self.logger.info("start_kernel", "Starting remote Jupyter kernel")

        try:
            kernel_info = await self.client.create_kernel()
            kernel_id = kernel_info["id"]
            self.kernels[kernel_id] = {"id": kernel_id, "info": kernel_info}

            self.logger.info(
                "start_kernel",
                "Kernel started",
                {"kernelId": kernel_id}
            )
            return {"id": kernel_id}

        except Exception as e:
            self.logger.error(
                "start_kernel",
                "Kernel start failed",
                {
                    "error": str(e),
                    "type": type(e).__name__,
                    "traceback": traceback.format_exc()
                }
            )
            # Re-raise to trigger @with_retry decorator
            raise

    async def execute_code(self, kernel_id: str, code: str) -> dict[str, list[dict[str, Any]]]:
        """Execute code on kernel with crash recovery.

        Args:
            kernel_id: Target kernel ID
            code: Python code to execute

        Returns:
            Dictionary with 'results' list of messages

        Raises:
            HTTPException: If kernel not found or execution fails
        """
        await self._wait_for_crash_recovery("execute_code")

        if kernel_id not in self.kernels:
            self.logger.warn("execute_code", "Kernel not found", {"kernelId": kernel_id})
            raise HTTPException(status_code=404, detail="Kernel not found")

        self.logger.info(
            "execute_code",
            "Execution requested",
            {"kernelId": kernel_id, "codeSize": len(code)}
        )

        try:
            results = await self.client.execute_code_via_websocket(kernel_id, code)

            for msg in results:
                msg_type = msg.get("header", {}).get("msg_type", "unknown")
                self.logger.info(
                    "execute_code",
                    "Message received",
                    {"kernelId": kernel_id, "msgType": msg_type}
                )

            self.logger.info(
                "execute_code",
                "Execution completed",
                {"kernelId": kernel_id, "messageCount": len(results)}
            )

            return {"results": results}

        except Exception as e:
            await self._handle_crash_recovery(kernel_id, e)
            raise HTTPException(status_code=404, detail="Kernel crashed")

    async def _handle_crash_recovery(self, kernel_id: str, error: Exception) -> None:
        """Handle kernel crash with recovery sleep.

        Args:
            kernel_id: Crashed kernel ID
            error: Exception that caused crash
        """
        self.logger.error(
            "execute_code",
            "Execution failed",
            {"kernelId": kernel_id, "error": str(error)}
        )

        self.crash_recovery.enter_crash_mode(self.crash_sleep_duration)

        self.logger.warn(
            "execute_code",
            "Entering crash recovery",
            {"kernelId": kernel_id, "sleepSeconds": self.crash_sleep_duration}
        )

        await asyncio.sleep(self.crash_sleep_duration)
        self.crash_recovery.exit_crash_mode()

        self.logger.info(
            "execute_code",
            "Shutting down crashed kernel",
            {"kernelId": kernel_id}
        )

        # Best effort kernel cleanup
        try:
            await self.client.delete_kernel(kernel_id)
        except Exception:
            pass  # Ignore cleanup errors

        self.kernels.pop(kernel_id, None)

    async def shutdown_kernel(self, kernel_id: str) -> dict[str, str]:
        """Shutdown kernel gracefully.

        Args:
            kernel_id: Kernel ID to shutdown

        Returns:
            Success message dictionary

        Raises:
            HTTPException: If kernel not found or shutdown fails
        """
        self.logger.info(
            "shutdown_kernel",
            "Shutdown requested",
            {"kernelId": kernel_id}
        )

        if kernel_id not in self.kernels:
            self.logger.warn("shutdown_kernel", "Kernel not found", {"kernelId": kernel_id})
            raise HTTPException(status_code=404, detail="Kernel not found")

        try:
            await self.client.delete_kernel(kernel_id)
            self.kernels.pop(kernel_id, None)

            self.logger.info(
                "shutdown_kernel",
                "Kernel shutdown successful",
                {"kernelId": kernel_id}
            )
            return {"message": f"Kernel {kernel_id} shutdown"}

        except Exception as e:
            self.logger.error(
                "shutdown_kernel",
                "Shutdown failed",
                {"kernelId": kernel_id, "error": str(e)}
            )
            raise HTTPException(status_code=500, detail="Shutdown failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Replaces deprecated @app.on_event("startup") and @app.on_event("shutdown").
    Manages JupyterClient and KernelManager lifecycle.

    Yields:
        None (FastAPI consumes this)
    """
    # Startup
    settings = Settings()
    logger = StructuredLogger(min_level=settings.log_level)

    logger.info("startup", f"Jupyter server URL: {settings.server_url}")

    async with JupyterClient(settings, logger) as client:
        kernel_manager = KernelManager(
            jupyter_client=client,
            logger=logger,
            crash_sleep_duration=settings.crash_sleep_duration
        )

        # Store in app state for routes to access
        app.state.kernel_manager = kernel_manager
        app.state.logger = logger

        logger.info("startup", "Application initialized")

        yield  # Application runs here

        # Shutdown
        logger.info("shutdown", "Application shutting down")


app = FastAPI(lifespan=lifespan)


class ExecuteCodeRequest(BaseModel):
    """Request model for code execution with validation."""

    id: str = Field(..., description="Kernel ID", min_length=1)
    code: str = Field(..., description="Python code to execute", min_length=1)

    @field_validator("code")
    @classmethod
    def validate_code_not_empty_whitespace(cls, v: str) -> str:
        """Ensure code is not just whitespace."""
        if not v.strip():
            raise ValueError("Code cannot be empty or whitespace only")
        return v


class ShutdownKernelRequest(BaseModel):
    """Request model for kernel shutdown."""
    id: str = Field(..., description="Kernel ID", min_length=1)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status dictionary
    """
    request.app.state.logger.info("health", "Health check requested")
    return {"status": "ok"}


@app.post("/start_kernel")
async def start_kernel(request: Request) -> dict[str, str]:
    """Start new Jupyter kernel.

    Returns:
        Dictionary with kernel 'id'

    Raises:
        HTTPException: If kernel start fails
    """
    manager: KernelManager = request.app.state.kernel_manager
    return await manager.start_kernel()


@app.post("/execute_code")
async def execute_code(req: ExecuteCodeRequest, request: Request) -> dict[str, list[dict]]:
    """Execute code on kernel.

    Args:
        req: Execution request with kernel ID and code

    Returns:
        Dictionary with execution results

    Raises:
        HTTPException: If kernel not found or execution fails
    """
    manager: KernelManager = request.app.state.kernel_manager
    return await manager.execute_code(req.id, req.code)


@app.post("/shutdown_kernel")
async def shutdown_kernel(req: ShutdownKernelRequest, request: Request) -> dict[str, str]:
    """Shutdown kernel.

    Args:
        req: Shutdown request with kernel ID

    Returns:
        Success message

    Raises:
        HTTPException: If kernel not found or shutdown fails
    """
    manager: KernelManager = request.app.state.kernel_manager
    return await manager.shutdown_kernel(req.id)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
