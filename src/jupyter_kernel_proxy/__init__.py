"""Jupyter Kernel Proxy - FastAPI server for remote Jupyter kernel management.

This package provides a proxy server that enables remote Jupyter kernel management
with code execution capabilities. It exposes REST APIs for starting kernels,
executing code via WebSocket, and managing kernel lifecycle.

Example:
    Basic usage:

    ```python
    from jupyter_kernel_proxy import Settings, StructuredLogger, JupyterClient, KernelManager

    settings = Settings(server_url="http://localhost:8888")
    logger = StructuredLogger()

    async with JupyterClient(settings, logger) as client:
        manager = KernelManager(client, logger)
        kernel = await manager.start_kernel()
        result = await manager.execute_code(kernel["id"], "print('Hello')")
    ```
"""

from .server import (
    # Core configuration
    Settings,
    LogLevel,

    # Logging
    StructuredLogger,

    # Client
    JupyterClient,

    # Management
    KernelManager,
    CrashRecoveryState,

    # FastAPI app
    app,

    # Request models
    ExecuteCodeRequest,
    ShutdownKernelRequest,
)

__version__ = "0.1.0"
__author__ = "Your Name"
__all__ = [
    "Settings",
    "LogLevel",
    "StructuredLogger",
    "JupyterClient",
    "KernelManager",
    "CrashRecoveryState",
    "app",
    "ExecuteCodeRequest",
    "ShutdownKernelRequest",
]
