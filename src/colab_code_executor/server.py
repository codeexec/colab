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


class ExecutionStatus(StrEnum):
    """Execution operation status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


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


@dataclass
class ExecutionState:
    """Tracks state of a code execution operation.

    Attributes:
        execution_id: Unique ID for this execution
        kernel_id: Kernel executing the code
        code: Code being executed
        status: Current execution status
        results: Execution results (when completed)
        error: Error message (when failed)
        created_at: Timestamp when execution was created
        started_at: Timestamp when execution started
        completed_at: Timestamp when execution completed/failed
    """
    execution_id: str
    kernel_id: str
    code: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    results: list[dict[str, Any]] | None = None
    error: str | None = None
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None

    def __post_init__(self):
        """Initialize timestamps."""
        if self.created_at == 0.0:
            self.created_at = time.time()


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
        self.executions: dict[str, ExecutionState] = {}

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

    async def execute_code(self, kernel_id: str, code: str) -> dict[str, str]:
        """Start code execution as a long-running operation.

        Args:
            kernel_id: Target kernel ID
            code: Python code to execute

        Returns:
            Dictionary with 'execution_id' for tracking

        Raises:
            HTTPException: If kernel not found
        """
        if kernel_id not in self.kernels:
            self.logger.warn("execute_code", "Kernel not found", {"kernelId": kernel_id})
            raise HTTPException(status_code=404, detail="Kernel not found")

        # Create execution state
        execution_id = str(uuid.uuid4())
        execution_state = ExecutionState(
            execution_id=execution_id,
            kernel_id=kernel_id,
            code=code
        )
        self.executions[execution_id] = execution_state

        self.logger.info(
            "execute_code",
            "Execution requested",
            {
                "kernelId": kernel_id,
                "executionId": execution_id,
                "codeSize": len(code),
                "codePreview": code[:200] if len(code) > 200 else code
            }
        )

        # Start background execution
        asyncio.create_task(self._execute_code_background(execution_id))

        return {"execution_id": execution_id}

    def _extract_final_output(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract final output from Jupyter kernel messages.

        Processes all messages and returns only the final/latest output including:
        - Latest stdout/stderr
        - Execute results (return values)
        - Errors and tracebacks

        Args:
            messages: List of raw Jupyter protocol messages

        Returns:
            Dictionary with processed output
        """
        output = {
            "stdout": "",
            "stderr": "",
            "result": None,
            "error": None,
            "traceback": None,
            "execution_count": None,
            "status": "ok"
        }

        # Collect all stream outputs
        stdout_parts = []
        stderr_parts = []

        for msg in messages:
            msg_type = msg.get("header", {}).get("msg_type")
            content = msg.get("content", {})

            # Collect stdout/stderr
            if msg_type == "stream":
                name = content.get("name")
                text = content.get("text", "")
                if name == "stdout":
                    stdout_parts.append(text)
                elif name == "stderr":
                    stderr_parts.append(text)

            # Collect execute_result (return values)
            elif msg_type == "execute_result":
                exec_count = content.get("execution_count")
                if exec_count is not None:
                    output["execution_count"] = exec_count
                self.logger.debug(
                    "extract_output",
                    "Found execute_result",
                    {"execution_count": exec_count, "content_keys": list(content.keys())}
                )
                # Get data in order of preference: text/plain, then others
                data = content.get("data", {})
                if "text/plain" in data:
                    output["result"] = data["text/plain"]
                elif data:
                    output["result"] = data

            # Collect display_data (plots, images, etc.)
            elif msg_type == "display_data":
                data = content.get("data", {})
                if not output["result"]:  # Only set if no execute_result
                    output["result"] = data

            # Collect errors
            elif msg_type == "error":
                output["status"] = "error"
                output["error"] = content.get("ename", "Error")
                output["traceback"] = content.get("traceback", [])

            # Get execution count from execute_reply
            elif msg_type == "execute_reply":
                exec_count = content.get("execution_count")
                if exec_count is not None:
                    output["execution_count"] = exec_count
                self.logger.debug(
                    "extract_output",
                    "Found execute_reply",
                    {"execution_count": exec_count, "status": content.get("status"), "content_keys": list(content.keys())}
                )
                if content.get("status") == "error":
                    output["status"] = "error"

        # Join all stdout/stderr parts
        output["stdout"] = "".join(stdout_parts)
        output["stderr"] = "".join(stderr_parts)

        self.logger.debug(
            "extract_output",
            "Final output",
            {
                "execution_count": output["execution_count"],
                "stdout_length": len(output["stdout"]),
                "stderr_length": len(output["stderr"]),
                "has_result": output["result"] is not None
            }
        )

        return output

    async def _execute_code_background(self, execution_id: str) -> None:
        """Execute code in background and update execution state with streaming.

        Args:
            execution_id: Execution ID to process
        """
        execution_state = self.executions.get(execution_id)
        if not execution_state:
            return

        kernel_id = execution_state.kernel_id
        code = execution_state.code

        try:
            await self._wait_for_crash_recovery("execute_code_background")

            # Update to RUNNING status
            execution_state.status = ExecutionStatus.RUNNING
            execution_state.started_at = time.time()
            execution_state.results = []  # Initialize empty results for streaming

            self.logger.info(
                "execute_code_background",
                "Execution started",
                {
                    "kernelId": kernel_id,
                    "executionId": execution_id,
                    "code": code
                }
            )

            # Execute code with streaming - handle WebSocket directly for incremental updates
            ws_url = self.client.settings.server_url.replace("http://", "ws://").replace("https://", "wss://")
            ws_url = f"{ws_url}/api/kernels/{kernel_id}/channels"
            if self.client.settings.token:
                ws_url = f"{ws_url}?token={self.client.settings.token}"

            msg_id = str(uuid.uuid4())
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
                self.logger.info(
                    "execute_code_background",
                    "WebSocket connected, sending execute request",
                    {"kernelId": kernel_id, "executionId": execution_id, "msgId": msg_id}
                )
                await ws.send(json.dumps(execute_msg))

                while True:
                    msg_raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                    msg = json.loads(msg_raw)

                    # Update results incrementally for streaming
                    execution_state.results.append(msg)

                    msg_type = msg.get("header", {}).get("msg_type", "unknown")
                    content = msg.get("content", {})

                    # Log message details based on type
                    log_meta = {
                        "kernelId": kernel_id,
                        "executionId": execution_id,
                        "msgType": msg_type
                    }

                    # Add specific content for different message types
                    if msg_type == "stream":
                        log_meta["streamName"] = content.get("name")
                        log_meta["text"] = content.get("text", "")[:100]  # First 100 chars
                        self.logger.info("execute_code_background", "Stream output", log_meta)
                    elif msg_type == "execute_result":
                        log_meta["executionCount"] = content.get("execution_count")
                        log_meta["dataKeys"] = list(content.get("data", {}).keys())
                        self.logger.info("execute_code_background", "Execute result", log_meta)
                    elif msg_type == "error":
                        log_meta["errorName"] = content.get("ename")
                        log_meta["errorValue"] = content.get("evalue")
                        self.logger.error("execute_code_background", "Execution error", log_meta)
                    elif msg_type == "status":
                        log_meta["executionState"] = content.get("execution_state")
                        self.logger.info("execute_code_background", "Status update", log_meta)
                    else:
                        self.logger.debug("execute_code_background", "Message received", log_meta)

                    # Check if execution is complete
                    if msg_type == "status":
                        if msg.get("content", {}).get("execution_state") == "idle":
                            if msg.get("parent_header", {}).get("msg_id") == msg_id:
                                self.logger.info(
                                    "execute_code_background",
                                    "Execution complete, kernel idle",
                                    {"kernelId": kernel_id, "executionId": execution_id}
                                )
                                break

            # Update to COMPLETED status
            execution_state.status = ExecutionStatus.COMPLETED
            execution_state.completed_at = time.time()

            # Extract and log final output
            final_output = self._extract_final_output(execution_state.results)

            self.logger.info(
                "execute_code_background",
                "Execution completed",
                {
                    "kernelId": kernel_id,
                    "executionId": execution_id,
                    "messageCount": len(execution_state.results),
                    "finalStatus": final_output.get("status"),
                    "hasStdout": bool(final_output.get("stdout")),
                    "hasStderr": bool(final_output.get("stderr")),
                    "hasResult": final_output.get("result") is not None,
                    "executionCount": final_output.get("execution_count")
                }
            )

        except Exception as e:
            # Update to FAILED status
            execution_state.status = ExecutionStatus.FAILED
            execution_state.error = str(e)
            execution_state.completed_at = time.time()

            self.logger.error(
                "execute_code_background",
                "Execution failed",
                {"kernelId": kernel_id, "executionId": execution_id, "error": str(e)}
            )

            # Handle crash recovery
            await self._handle_crash_recovery(kernel_id, e)

    def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        """Get status of a code execution.

        Args:
            execution_id: Execution ID to check

        Returns:
            Dictionary with execution status and output (including partial output while running)

        Raises:
            HTTPException: If execution not found
        """
        execution_state = self.executions.get(execution_id)
        if not execution_state:
            self.logger.warn("get_execution_status", "Execution not found", {"executionId": execution_id})
            raise HTTPException(status_code=404, detail="Execution not found")

        response = {
            "execution_id": execution_state.execution_id,
            "kernel_id": execution_state.kernel_id,
            "status": execution_state.status.value,
            "created_at": execution_state.created_at,
            "started_at": execution_state.started_at,
            "completed_at": execution_state.completed_at,
        }

        # Return output for both RUNNING and COMPLETED states (streaming output)
        if execution_state.results and len(execution_state.results) > 0:
            output = self._extract_final_output(execution_state.results)
            response["output"] = output

        if execution_state.status == ExecutionStatus.FAILED and execution_state.error:
            response["error"] = execution_state.error

        self.logger.debug(
            "get_execution_status",
            "Status retrieved",
            {
                "executionId": execution_id,
                "status": execution_state.status.value,
                "messageCount": len(execution_state.results) if execution_state.results else 0
            }
        )

        return response

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
    logger: StructuredLogger = request.app.state.logger
    logger.info("api_start_kernel", "POST /start_kernel endpoint called")
    manager: KernelManager = request.app.state.kernel_manager
    result = await manager.start_kernel()
    logger.info(
        "api_start_kernel",
        "Kernel started via API",
        {"kernelId": result.get("id")}
    )
    return result


@app.post("/execute_code")
async def execute_code(req: ExecuteCodeRequest, request: Request) -> dict[str, str]:
    """Start code execution as a long-running operation.

    Args:
        req: Execution request with kernel ID and code

    Returns:
        Dictionary with execution_id for tracking

    Raises:
        HTTPException: If kernel not found
    """
    logger: StructuredLogger = request.app.state.logger
    logger.info(
        "api_execute_code",
        "POST /execute_code endpoint called",
        {"kernelId": req.id, "codeLength": len(req.code)}
    )
    manager: KernelManager = request.app.state.kernel_manager
    result = await manager.execute_code(req.id, req.code)
    logger.info(
        "api_execute_code",
        "Execution initiated",
        {"kernelId": req.id, "executionId": result.get("execution_id")}
    )
    return result


@app.get("/execution_status/{execution_id}")
async def get_execution_status(execution_id: str, request: Request) -> dict[str, Any]:
    """Get status of a code execution operation.

    Args:
        execution_id: Execution ID to check

    Returns:
        Dictionary with execution status, results, and metadata

    Raises:
        HTTPException: If execution not found
    """
    logger: StructuredLogger = request.app.state.logger
    logger.debug(
        "api_execution_status",
        "GET /execution_status endpoint called",
        {"executionId": execution_id}
    )
    manager: KernelManager = request.app.state.kernel_manager
    status = manager.get_execution_status(execution_id)
    logger.debug(
        "api_execution_status",
        "Status retrieved",
        {"executionId": execution_id, "status": status.get("status")}
    )
    return status


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
    logger: StructuredLogger = request.app.state.logger
    logger.info(
        "api_shutdown_kernel",
        "POST /shutdown_kernel endpoint called",
        {"kernelId": req.id}
    )
    manager: KernelManager = request.app.state.kernel_manager
    result = await manager.shutdown_kernel(req.id)
    logger.info(
        "api_shutdown_kernel",
        "Kernel shutdown via API",
        {"kernelId": req.id}
    )
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
